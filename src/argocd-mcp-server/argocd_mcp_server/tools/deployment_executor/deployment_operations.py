"""Deployment Operations Tools - 7 tools for deployment, diff, sync, logs, and rollback."""

from typing import Any, Dict, List, Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from argocd_mcp_server.tools.base import BaseTool


class DeploymentExecutorTools(BaseTool):
    """Tools for executing and monitoring ArgoCD deployments."""

    toolset_name: str = "deployments"

    def register(self, mcp_instance: Any) -> None:
        """Register deployment tools with FastMCP."""

        if self.should_register_tool(is_read_only=True):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Application Diff",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_application_diff(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application.",
                ),
                revision: Optional[str] = Field(
                    default=None,
                    description="Optional Git branch, tag, or commit SHA to compare against live state.",
                ),
                validate: bool = Field(
                    default=True,
                    description="If True, also runs a dry-run sync check to validate Kubernetes manifests.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Compare live cluster state against target Git manifests and optionally validate via dry-run."""
                await self._log_info(
                    ctx,
                    f"Getting diff for {app_name}",
                    extra={"app_name": app_name, "revision": revision, "validate": validate},
                )
                return await self.argocd_service.get_application_diff(
                    app_name=app_name,
                    revision=revision,
                    validate=validate,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Sync Status",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_sync_status(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Get current sync status, active operation phase, per-resource sync results, and recent history."""
                await self._log_info(
                    ctx,
                    f"Getting sync status for {app_name}",
                    extra={"app_name": app_name},
                )
                return await self.argocd_service.get_sync_status(app_name=app_name)

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Application Logs",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_application_logs(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application.",
                ),
                pod_name: Optional[str] = Field(
                    default=None,
                    description="Specific pod name. If omitted, inspects up to 5 pods in the application.",
                ),
                container: Optional[str] = Field(
                    default=None,
                    description="Container name within the pod (optional).",
                ),
                tail_lines: int = Field(
                    default=50,
                    ge=1,
                    le=200,
                    description="Number of recent log lines to fetch per pod (1-200).",
                ),
                since_seconds: Optional[int] = Field(
                    default=None,
                    ge=1,
                    description="Only return logs newer than this many seconds.",
                ),
                errors_only: bool = Field(
                    default=False,
                    description="If True, filter log output to lines matching error/fatal/exception/panic signatures.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Retrieve and summarize pod logs for an application with NDJSON stream parsing and error detection."""
                await self._log_info(
                    ctx,
                    f"Getting pod logs for {app_name}",
                    extra={"app_name": app_name, "pod_name": pod_name, "errors_only": errors_only},
                )
                return await self.argocd_service.get_application_logs(
                    app_name=app_name,
                    pod_name=pod_name,
                    container=container,
                    tail_lines=tail_lines,
                    since_seconds=since_seconds,
                    errors_only=errors_only,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Refresh Application",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def refresh_application(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application to refresh.",
                ),
                mode: Literal["normal", "hard"] = Field(
                    default="normal",
                    description="Refresh mode: 'normal' (re-compare against cached Git state) or 'hard' (invalidate manifest cache and re-read Git).",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Trigger a soft ('normal') or manifest-cache-invalidating ('hard') refresh on an application."""
                await self._log_info(
                    ctx,
                    f"Refreshing application {app_name} (mode={mode})",
                    extra={"app_name": app_name, "mode": mode},
                )
                return await self.argocd_service.refresh_application(
                    app_name=app_name,
                    mode=mode,
                )

        if self.should_register_tool(is_read_only=False, supports_dry_run=True):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Sync Application",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def sync_application(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application to sync.",
                ),
                revision: Optional[str] = Field(
                    default=None,
                    description="Optional Git revision (branch, tag, SHA) to sync. Defaults to the app's configured targetRevision.",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Defaults to True (preview only). Set False to apply changes to the cluster.",
                ),
                prune: bool = Field(
                    default=False,
                    description="If True, delete cluster resources that are no longer present in Git.",
                ),
                force: bool = Field(
                    default=False,
                    description="If True, force-apply resources during sync.",
                ),
                resources: Optional[List[Dict[str, str]]] = Field(
                    default=None,
                    description="Optional selective sync filter list: [{'group': '', 'kind': 'Deployment', 'name': 'web', 'namespace': 'default'}].",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Set True after operator confirmation when executing with prune=True and dry_run=False.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Preview (dry_run=True) or execute (dry_run=False) an ArgoCD application sync operation."""
                self.argocd_service._check_write_access(
                    "application sync", allow_dry_run=True, dry_run=dry_run
                )
                if not dry_run and prune:
                    gate = await self.confirm_destructive_action(
                        ctx,
                        f"sync application '{app_name}' with prune=True (deletes resources removed from Git)",
                        confirm=confirm,
                        impact_preview={
                            "operation": "sync_application",
                            "app_name": app_name,
                            "revision": revision or "HEAD",
                            "prune": True,
                            "force": force,
                            "effect": "Applies Git manifests and deletes any cluster resources no longer defined in Git.",
                        },
                    )
                    if gate is not None:
                        return gate

                await self._log_info(
                    ctx,
                    f"Syncing application {app_name} (dry_run={dry_run}, prune={prune})",
                    extra={"app_name": app_name, "dry_run": dry_run, "prune": prune},
                )
                return await self.argocd_service.sync_application(
                    app_name=app_name,
                    revision=revision,
                    dry_run=dry_run,
                    prune=prune,
                    force=force,
                    resources=resources,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Rollback Application",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def rollback_application(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application to roll back.",
                ),
                history_id: Optional[int] = Field(
                    default=None,
                    description="Deployment history ID from get_application_details. Omit to target the immediately preceding deployment.",
                ),
                dry_run: bool = Field(
                    default=True,
                    description="Defaults to True (preview target revision and check auto-sync blocker). Set False to execute rollback.",
                ),
                prune: bool = Field(
                    default=False,
                    description="If True, prune resources created since the target deployment.",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Set True after operator confirmation when executing rollback with dry_run=False.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Preview (dry_run=True) or execute (dry_run=False) an application rollback to a specific deployment history ID."""
                self.argocd_service._check_write_access(
                    "application rollback", allow_dry_run=True, dry_run=dry_run
                )
                if not dry_run:
                    target_desc = (
                        f"history ID {history_id}" if history_id is not None else "previous deployment"
                    )
                    gate = await self.confirm_destructive_action(
                        ctx,
                        f"rollback application '{app_name}' to {target_desc} (prune={prune})",
                        confirm=confirm,
                        impact_preview={
                            "operation": "rollback_application",
                            "app_name": app_name,
                            "history_id": history_id,
                            "prune": prune,
                            "effect": f"Reverts cluster resources for '{app_name}' to {target_desc}.",
                        },
                    )
                    if gate is not None:
                        return gate

                await self._log_warning(
                    ctx,
                    f"Rolling back application {app_name} (history_id={history_id}, dry_run={dry_run})",
                    extra={"app_name": app_name, "history_id": history_id, "dry_run": dry_run},
                )
                return await self.argocd_service.rollback_application(
                    app_name=app_name,
                    history_id=history_id,
                    dry_run=dry_run,
                    prune=prune,
                )

        if self.should_register_tool(is_read_only=False):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Cancel Deployment",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def cancel_deployment(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application whose running sync operation should be terminated.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Terminate an ongoing sync operation on an application."""
                await self._log_warning(
                    ctx,
                    f"Cancelling active deployment operation for {app_name}",
                    extra={"app_name": app_name},
                )
                return await self.argocd_service.cancel_deployment(app_name=app_name)
