"""Policies toolset (T7-T9): HTTP/TCP Middlewares, TLSOption/TLSStore, and ServersTransport/ServersTransportTCP."""

from typing import Any, Dict, Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from traefik_mcp_server.models.schemas import (
    ALL_MIDDLEWARE_TYPES,
    ExecutionResult,
)
from traefik_mcp_server.tools.base import BaseTool, confirm_destructive_action


class PolicyTools(BaseTool):
    """Tools for configuring Traefik v3 Middlewares, TLS policies, and backend ServersTransports."""

    def register(self, mcp_instance) -> None:
        if not self.should_register("policies", is_write=True):
            return

        # ── T7: traefik_configure_middleware (6 params) ────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Traefik HTTP or TCP Middleware",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_configure_middleware(
            name: str = Field(..., min_length=1, description="Middleware or MiddlewareTCP name"),
            type: ALL_MIDDLEWARE_TYPES = Field(
                ...,
                description="Middleware type (e.g. 'rate_limit', 'circuit_breaker', 'headers', 'ip_allow_list', 'forward_auth', 'strip_prefix', 'chain')",
            ),
            spec: Dict[str, Any] = Field(
                ...,
                description="Type-specific middleware configuration dictionary",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            protocol: Literal["http", "tcp"] = Field(
                default="http",
                description="Middleware protocol ('http' -> Middleware, 'tcp' -> MiddlewareTCP)",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), validate against CRD schema and return YAML + diff preview",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create or update a Traefik v3 HTTP Middleware or TCP MiddlewareTCP (<= 8 parameters).

            Enforces CRD OpenAPI schema gating (rejecting unsupported fields such as ipDenyList unless installed),
            rejects inline basicAuth/digestAuth passwords in favor of Secret references, and detects chain cycles.
            """
            self.check_write_access("traefik_configure_middleware")
            try:
                res = await self.traefik_service.configure_middleware(
                    name=name,
                    namespace=namespace,
                    protocol=protocol,
                    middleware_type=type,
                    spec=spec,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_configure_middleware", namespace=namespace, resource_name=name)

        # ── T8: traefik_configure_tls_policy (6 params) ────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Traefik TLSOption or TLSStore Policy",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_configure_tls_policy(
            kind: Literal["TLSOption", "TLSStore"] = Field(
                ...,
                description="TLS policy resource kind ('TLSOption' or 'TLSStore')",
            ),
            name: str = Field(
                ...,
                min_length=1,
                description="Policy name (must be 'default' for TLSStore)",
            ),
            spec: Dict[str, Any] = Field(
                ...,
                description="TLSOption (profile, min_version, cipher_suites, client_auth) or TLSStore (default_certificate_secret) spec",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            dry_run: bool = Field(
                default=True,
                description="If True (default), validate and return YAML + diff preview without mutating cluster",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm global default TLSOption or default TLSStore certificate mutations when dry_run=False",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create or update a Traefik TLSOption policy or default TLSStore (<= 8 parameters).

            Requires confirmation when modifying a 'default' TLSOption in the Traefik controller namespace
            or changing a default TLSStore certificate (high blast radius across all routes).
            """
            self.check_write_access("traefik_configure_tls_policy")
            try:
                is_global_blast_radius = (
                    kind == "TLSStore"
                    or (kind == "TLSOption" and name == "default")
                    or bool((spec or {}).get("sni_strict") or (spec or {}).get("sniStrict") or str((spec or {}).get("profile", "")).lower() in ("modern", "intermediate"))
                )
                if is_global_blast_radius and not dry_run:
                    confirmed = await confirm_destructive_action(
                        ctx=ctx,
                        action_summary=f"Apply high-blast-radius {kind} '{namespace}/{name}'",
                        confirm=confirm,
                        resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
                    )
                    if not confirmed:
                        return ExecutionResult(
                            status="cancelled",
                            summary=f"Applying {kind} '{namespace}/{name}' (default policy or sniStrict=true) requires confirmation. Pass confirm=True after verifying certificate SAN coverage.",
                            dry_run=False,
                            resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
                        )

                res = await self.traefik_service.configure_tls_policy(
                    kind=kind,
                    name=name,
                    namespace=namespace,
                    spec=spec,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_configure_tls_policy", namespace=namespace, resource_name=name)

        # ── T9: traefik_configure_servers_transport (5 params) ─────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Traefik Backend ServersTransport",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_configure_servers_transport(
            name: str = Field(..., min_length=1, description="ServersTransport or ServersTransportTCP name"),
            spec: Dict[str, Any] = Field(
                ...,
                description="Backend transport settings (forwarding_timeouts, server_name, root_cas, certificates, max_idle_conns_per_host, insecure_skip_verify)",
            ),
            protocol: Literal["http", "tcp"] = Field(
                default="http",
                description="Transport protocol ('http' -> ServersTransport, 'tcp' -> ServersTransportTCP)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            dry_run: bool = Field(
                default=True,
                description="If True (default), validate and return YAML + diff preview without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create or update a Traefik ServersTransport or ServersTransportTCP CRD (<= 8 parameters)."""
            self.check_write_access("traefik_configure_servers_transport")
            try:
                res = await self.traefik_service.configure_servers_transport(
                    protocol=protocol,
                    name=name,
                    namespace=namespace,
                    spec=spec,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_configure_servers_transport", namespace=namespace, resource_name=name)
