"""MCP tool for NGINX → Traefik migration (apply, generate, revert).

Read-only operations are exposed as MCP **resources** (not this tool):
  traefik://migration/nginx-ingress-scan[/{namespace}]    — inventory + paths + values
  traefik://migration/nginx-ingress-analyze[/{namespace}]  — full analysis report
  traefik://migration/nginx-runbook[/{namespace}]          — migration runbook (default settings)

This tool handles:
  - action=apply / generate: Middleware CRDs + Ingress patches (or YAML-only preview)
  - action=revert: single-Ingress rollback (ingress_name required)
"""

import json
from typing import Any, Dict, Literal, Optional

from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations

from traefik_mcp_server.services.nginx_migration_service import slim_migrate_tool_payload
from traefik_mcp_server.tools.base import BaseTool


class NginxMigrationTools(BaseTool):
    """MCP tool: apply migration or generate with agent overrides."""

    def register(self, mcp_instance) -> None:
        """Register the migration tool with FastMCP."""

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="NGINX Migration",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_nginx_migration(
            namespace: str = Field(
                ...,
                description=(
                    "Kubernetes namespace. For apply/generate: migration scope. "
                    "For revert: namespace of the Ingress to revert."
                ),
            ),
            action: Literal["apply", "generate", "revert"] = Field(
                default="apply",
                description=(
                    "apply: mutate cluster (Middleware + Ingress patches) when target=traefik; "
                    "generate: same migration logic with apply=false (preview / migration_plan); "
                    "revert: undo one Ingress (requires ingress_name, MCP_ALLOW_WRITE=true)."
                ),
            ),
            target: Literal["traefik", "gateway-api"] = Field(
                default="traefik",
                description="apply/generate only: traefik vs gateway-api output.",
            ),
            switch: bool = Field(
                default=False,
                description=(
                    "apply only: patch ingressClassName from nginx to traefik for cutover."
                ),
            ),
            migration_plan: Optional[Dict[str, Any]] = Field(
                default=None,
                description=(
                    "apply/generate only: per-Ingress overrides (ignore_annotations, inject_middlewares)."
                ),
            ),
            ingress_name: Optional[str] = Field(
                default=None,
                description="revert only: Ingress resource name to roll back to pre-migration state.",
            ),
            ctx: Optional[Context] = None,
        ) -> str:
            """NGINX → Traefik migration: apply, generate preview, or revert.

            Translates NGINX Ingress rules to Traefik CRDs.

            **WARNING: Mutates live traffic routing (action=apply, switch=True).**

            Returns:
            - JSON string or markdown response.

            When NOT to use:
            - For reading state → use `read_resource traefik://migration/...`.
            """
            assert self.nginx_migration_service is not None

            if action == "revert":
                if not ingress_name or not str(ingress_name).strip():
                    raise ValueError("action=revert requires ingress_name")
                if ctx:
                    await ctx.info(f"Reverting migration for {namespace}/{ingress_name}")
                if not self.config.allow_write:
                    err = {
                        "status": "blocked",
                        "error": (
                            "Revert requires MCP_ALLOW_WRITE=true. "
                            "Set the environment variable and restart the server."
                        ),
                    }
                    if ctx:
                        await ctx.error(err["error"])
                    return json.dumps(err, indent=2)
                try:
                    result = await self.nginx_migration_service.revert_migration(
                        namespace=namespace,
                        ingress_name=ingress_name.strip(),
                    )
                    if result.get("status") == "error":
                        if ctx:
                            await ctx.error(f"Revert failed: {result.get('error')}")
                    else:
                        if ctx:
                            await ctx.info(result.get("message", "Revert complete"))
                    return json.dumps(result, indent=2, default=str)
                except Exception as e:
                    error_msg = f"Revert failed: {e}"
                    if ctx:
                        await ctx.error(error_msg)
                    return json.dumps(
                        {"status": "error", "error": error_msg}, indent=2,
                    )

            apply_flag = action == "apply"
            scope = f"namespace {namespace}"
            log_action = "apply" if apply_flag else "generate with overrides"
            if ctx:
                await ctx.info(f"Migrating NGINX → Traefik ({log_action}) in {scope}")

            try:
                result = await self.nginx_migration_service.migrate(
                    namespace=namespace,
                    target=target,
                    apply=apply_flag,
                    switch=switch,
                    migration_plan=migration_plan,
                )
                if result.get("status") == "error":
                    if ctx:
                        await ctx.error(f"Migration failed: {result.get('error')}")
                    return (
                        f"❌ **Migration Failed**\n{result.get('error')}\n\n"
                        "**Next Steps for Agent:**\n"
                        "- Verify the namespace exists.\n"
                        "- Check if there are valid Ingress resources to migrate using `read_resource traefik://migration/nginx-ingress-scan`."
                    )

                slim = slim_migrate_tool_payload(result, namespace)
                bs = (slim.get("migration") or {}).get("bundleSummary") or {}
                
                out_lines = [
                    f"# NGINX to Traefik Migration: {result.get('status', 'success').capitalize()}",
                    f"Generated {bs.get('total_files', 0)} files in bundle."
                ]
                
                if switch:
                    sr = slim.get("switch_result", {})
                    if sr.get("status") == "blocked":
                        out_lines.append(f"\n❌ **Switch Blocked:** {sr.get('error', 'Requires MCP_ALLOW_WRITE=true')}")
                    elif sr.get("status") == "skipped":
                        out_lines.append(f"\n⚠️ **Switch Skipped:** {sr.get('message', sr.get('reason'))}")
                    else:
                        summary = sr.get("summary", {})
                        out_lines.append(f"\n✅ **Instant Switch Successful ({summary.get('switched', 0)} ingresses patched)**")
                        out_lines.append(
                            "\n**Next Steps for Agent (Finalizing Migration):**\n"
                            "1. Ask the User: *'The traffic has been instantly switched to Traefik. "
                            "To migrate it 100%, I can safely delete the legacy NGINX Ingress Controller "
                            "from your cluster. Let me know!'*\n"
                            "2. Apply the cleanup manifest to preserve IngressClass before removing NGINX:\n"
                            "```bash\n"
                            "cat <<EOF | kubectl apply -f -\n"
                            "apiVersion: networking.k8s.io/v1\n"
                            "kind: IngressClass\n"
                            "metadata:\n"
                            "  name: nginx\n"
                            "  annotations:\n"
                            "    ingressclass.kubernetes.io/is-default-class: \"false\"\n"
                            "    helm.sh/resource-policy: keep\n"
                            "spec:\n"
                            "  controller: k8s.io/ingress-nginx\n"
                            "EOF\n"
                            "```\n"
                            "3. Call the `run_command` tool to execute `bash 06-cleanup/02-remove-nginx.sh`."
                        )
                elif apply_flag and "apply_result" in slim:
                    ar = slim["apply_result"]
                    if ar.get("status") == "blocked":
                        out_lines.append(f"\n❌ **Apply Blocked:** {ar.get('error', 'Requires MCP_ALLOW_WRITE=true')}")
                        out_lines.append("\n**Next Steps for Agent:**")
                        out_lines.append("1. The cluster was NOT mutated because `MCP_ALLOW_WRITE` is false.")
                        out_lines.append("2. Please restart the MCP server with `MCP_ALLOW_WRITE=true` to apply changes.")
                        out_lines.append(f"3. You can still view the generated YAML via `read_resource traefik://migration/nginx-runbook/{namespace}`.")
                    elif ar.get("status") == "skipped":
                        out_lines.append(f"\n⚠️ **Apply Skipped:** {ar.get('message', ar.get('reason'))}")
                    else:
                        s = ar.get("summary", {})
                        out_lines.append("\n✅ **Apply Successful**")
                        out_lines.append(f"- Applied resources: {s.get('applied', 0)}")
                        out_lines.append(f"- Errors: {s.get('errors', 0)}")
                        if s.get("errors", 0) > 0:
                            out_lines.append("\nSome resources failed to apply. Please check the server logs for Kubernetes API errors.")
                        
                        out_lines.append(
                            "\n**Next Steps for Agent (Validation & Cutover):**\n"
                            "1. **Validate via Application Tests:** Run manual `curl` commands testing the endpoints. E.g.: `curl -H \"Host: <ingress-host>\" http://<traefik-loadbalancer-ip>`\n"
                            "2. **Cutover Traffic:** Once verified, you have two options for cutover:\n"
                            "   - **Option A (DNS):** Safely add the Traefik LoadBalancer IP to DNS (side-by-side strategy).\n"
                            "   - **Option B (Instant Switch):** You can instantly switch traffic to Traefik within the cluster. "
                            "Use this tool (`traefik_nginx_migration`) again with `action=apply` and `switch=True`."
                        )
                else:
                    out_lines.append("\n✅ **Generation Successful** (action=generate)")
                    out_lines.append("The artifacts were successfully generated with your overrides.")

                if not switch:
                    out_lines.append("\n## Read-Only Runbook")
                    out_lines.append(f"For the full runbook (inline YAML, DNS cutover, scripts), use:\n`read_resource traefik://migration/nginx-runbook/{namespace}`")

                final_msg = "\n".join(out_lines)
                if ctx:
                    await ctx.info(f"Migration completed for {namespace}")
                return final_msg
            except Exception as e:
                error_msg = f"Migration failed: {e}"
                if ctx:
                    await ctx.error(error_msg)
                return f"❌ **Migration Failed**\n{error_msg}"
