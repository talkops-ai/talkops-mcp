"""Traffic toolset (T1-T6): HTTP routing, weighted canary/blue-green services, weight shifts, mirroring, route patching, and TCP/UDP routing."""

from typing import Any, Dict, List, Literal, Optional, Union
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from traefik_mcp_server.models.schemas import (
    BackendRef,
    ExecutionResult,
    HealthCheck,
    HttpRouteRule,
    MirroringSpec,
    RouteChanges,
    RouteTLS,
    StickyCookie,
    TcpUdpRouteRule,
    WeightedExposeConfig,
)
from traefik_mcp_server.tools.base import BaseTool, confirm_destructive_action


class TrafficTools(BaseTool):
    """Tools for managing Traefik v3 HTTP, weighted, mirrored, and TCP/UDP traffic routing."""

    def register(self, mcp_instance) -> None:
        if not self.should_register("traffic", is_write=True):
            return

        # ── T1: traefik_configure_http_route (7 params) ────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Traefik HTTP IngressRoute",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_configure_http_route(
            name: str = Field(..., min_length=1, description="IngressRoute name (DNS-1123)"),
            rules: List[HttpRouteRule] = Field(
                ...,
                min_length=1,
                description="One or more HTTP routing rules (match, middlewares, services, priority)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            entry_points: List[str] = Field(
                default_factory=lambda: ["websecure"],
                description="Traefik entryPoints (e.g. ['websecure'])",
            ),
            tls: Optional[RouteTLS] = Field(
                default=None,
                description="Optional TLS secretName, certResolver, domains, or TLSOption reference",
            ),
            ingress_class: Optional[str] = Field(
                default=None,
                description="Optional kubernetes.io/ingress.class annotation value",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), validate and return YAML + diff preview without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create or update a Traefik v3 HTTP IngressRoute (<= 8 parameters).

            Compiles and lints v3 match expressions, checks backend Service/port/endpoint readiness,
            verifies TLS SAN coverage, and defaults to dry_run=True.
            """
            self.check_write_access("traefik_configure_http_route")
            try:
                res = await self.traefik_service.configure_http_route(
                    name=name,
                    namespace=namespace,
                    rules=rules,
                    entry_points=entry_points,
                    tls=tls,
                    ingress_class=ingress_class,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_configure_http_route", namespace=namespace, resource_name=name)

        # ── T2: traefik_configure_weighted_service (7 params) ──────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Traefik Weighted Canary/Blue-Green Service",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_configure_weighted_service(
            name: str = Field(..., min_length=1, description="TraefikService name (e.g. 'payments-wrr')"),
            backends: List[BackendRef] = Field(
                ...,
                min_length=2,
                description="Weighted backend Services (at least 2, each with 'name', 'port', and 'weight')",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            sticky: Optional[StickyCookie] = Field(
                default=None,
                description="Optional WRR-level sticky session cookie settings",
            ),
            health_check: Optional[Union[bool, HealthCheck, Dict[str, Any]]] = Field(
                default=False,
                description="Enable active healthCheck across weighted backends (bool or HealthCheck dict e.g. {'path': '/', 'interval': '10s', 'timeout': '3s'})",
            ),
            expose: Optional[WeightedExposeConfig] = Field(
                default=None,
                description="Optional IngressRoute exposure settings to create/update in the same call",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), validate and return YAML + diff preview without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create or update a weighted TraefikService for canary or blue-green traffic splitting, and optionally expose it via an IngressRoute in one call (<= 8 parameters)."""
            self.check_write_access("traefik_configure_weighted_service")
            try:
                res = await self.traefik_service.configure_weighted_service(
                    name=name,
                    namespace=namespace,
                    backends=backends,
                    sticky=sticky,
                    health_check=health_check,
                    expose=expose,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_configure_weighted_service", namespace=namespace, resource_name=name)

        # ── T3: traefik_set_traffic_weights (5 params) ─────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Set Traefik Traffic Weights",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_set_traffic_weights(
            name: str = Field(..., min_length=1, description="Weighted TraefikService name"),
            weights: Dict[str, int] = Field(
                ...,
                description="Map of backend Service name to integer weight (e.g. {'api-stable': 80, 'api-canary': 20})",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            expected_resource_version: Optional[str] = Field(
                default=None,
                description="Optional resourceVersion from dry-run preview for optimistic concurrency control",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), preview weight shift and return current resource_version before applying",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Shift traffic weights on an existing weighted TraefikService (<= 8 parameters).

            Blocks routing weight > 0 to backends with 0 ready endpoints (WEIGHT_TO_EMPTY_BACKEND),
            blocks setting all weights to 0 (ALL_WEIGHTS_ZERO), refuses Argo Rollouts-managed services,
            and defaults to dry_run=True.
            """
            self.check_write_access("traefik_set_traffic_weights")
            try:
                res = await self.traefik_service.set_traffic_weights(
                    name=name,
                    namespace=namespace,
                    weights=weights,
                    expected_resource_version=expected_resource_version,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_set_traffic_weights", namespace=namespace, resource_name=name)

        # ── T4: traefik_configure_traffic_mirroring (7 params) ─────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Traefik Shadow Traffic Mirroring",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_configure_traffic_mirroring(
            name: str = Field(..., min_length=1, description="Mirroring TraefikService name"),
            action: Literal["enable", "update", "disable"] = Field(
                default="enable",
                description="Mirroring operation: 'enable', 'update', or 'disable'",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            spec: Optional[MirroringSpec] = Field(
                default=None,
                description="Primary backend and mirror targets (required for 'enable' and 'update')",
            ),
            route_name: Optional[str] = Field(
                default=None,
                description="Optional IngressRoute name to point at (or restore from) the mirroring service",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), preview mirroring configuration without mutating cluster",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm disabling traffic mirroring when dry_run=False",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Enable, update, or disable shadow traffic mirroring via a TraefikService (<= 8 parameters)."""
            self.check_write_access("traefik_configure_traffic_mirroring")
            try:
                if not dry_run:
                    confirmed = await confirm_destructive_action(
                        ctx=ctx,
                        action_summary=f"Apply traffic mirroring ({action}) on TraefikService '{namespace}/{name}'",
                        confirm=confirm,
                        resource_uri=f"traefik://manifests/TraefikService/{namespace}/{name}",
                    )
                    if not confirmed:
                        return ExecutionResult(
                            status="cancelled",
                            summary=f"Traffic mirroring ({action}) on '{namespace}/{name}' was not confirmed. Pass confirm=True after user approval.",
                            dry_run=False,
                            resource_uri=f"traefik://manifests/TraefikService/{namespace}/{name}",
                        )

                res = await self.traefik_service.configure_traffic_mirroring(
                    name=name,
                    namespace=namespace,
                    action=action,
                    spec=spec,
                    route_name=route_name,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_configure_traffic_mirroring", namespace=namespace, resource_name=name)

        # ── T5: traefik_update_route (6 params) ────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Update Existing Traefik Route",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_update_route(
            name: str = Field(..., min_length=1, description="Route resource name"),
            changes: RouteChanges = Field(
                ...,
                description="Targeted modifications: middlewares (ordered attach/detach/replace), tls (set/remove), entry_points, priority, or backend options",
            ),
            route_kind: Literal["IngressRoute", "IngressRouteTCP", "Ingress"] = Field(
                default="IngressRoute",
                description="Route resource kind to patch ('IngressRoute', 'IngressRouteTCP', or 'Ingress')",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            dry_run: bool = Field(
                default=True,
                description="If True (default), preview the patched manifest and unified diff without mutating cluster",
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm destructive route updates (e.g. removing TLS or clearing all middlewares)",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Patch an existing IngressRoute, IngressRouteTCP, or Kubernetes Ingress without restating the full resource (<= 8 parameters).

            Writes to the IngressRoute spec for CRD routes, or to Traefik router/Service annotations for Kubernetes Ingress routes.
            Refuses Ingress objects claimed by the NGINX Ingress provider to prevent mixing annotation sets.
            """
            self.check_write_access("traefik_update_route")
            try:
                is_destructive_patch = bool(
                    (changes.tls and changes.tls.get("remove"))
                    or (changes.middlewares and changes.middlewares.action == "replace" and not changes.middlewares.refs)
                )
                if is_destructive_patch and not dry_run:
                    confirmed = await confirm_destructive_action(
                        ctx=ctx,
                        action_summary=f"Remove TLS or clear all middlewares on {route_kind} '{namespace}/{name}'",
                        confirm=confirm,
                        resource_uri=f"traefik://manifests/{route_kind}/{namespace}/{name}",
                    )
                    if not confirmed:
                        return ExecutionResult(
                            status="cancelled",
                            summary=f"Destructive update on {route_kind} '{namespace}/{name}' was not confirmed. Pass confirm=True after user approval.",
                            dry_run=False,
                            resource_uri=f"traefik://manifests/{route_kind}/{namespace}/{name}",
                        )

                res = await self.traefik_service.update_route(
                    route_kind=route_kind,
                    name=name,
                    namespace=namespace,
                    changes=changes,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_update_route", namespace=namespace, resource_name=name)

        # ── T6: traefik_configure_tcp_udp_route (7 params) ─────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Traefik TCP or UDP Route",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def traefik_configure_tcp_udp_route(
            name: str = Field(..., min_length=1, description="IngressRouteTCP or IngressRouteUDP name"),
            routes: List[TcpUdpRouteRule] = Field(
                ...,
                min_length=1,
                description="TCP/UDP route rules (match HostSNI for TCP, services with port/weight/proxyProtocol)",
            ),
            protocol: Literal["tcp", "udp"] = Field(
                default="tcp",
                description="Transport protocol ('tcp' -> IngressRouteTCP, 'udp' -> IngressRouteUDP)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            entry_points: Optional[List[str]] = Field(
                default=None,
                description="Traefik TCP or UDP entryPoints (e.g. ['tcp'] or ['udp'])",
            ),
            tls: Optional[RouteTLS] = Field(
                default=None,
                description="TCP TLS termination or passthrough settings (TCP only; required when HostSNI != '*')",
            ),
            dry_run: bool = Field(
                default=True,
                description="If True (default), validate and return YAML + diff preview without mutating cluster",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            """Create or update a Traefik IngressRouteTCP or IngressRouteUDP (<= 8 parameters)."""
            self.check_write_access("traefik_configure_tcp_udp_route")
            try:
                res = await self.traefik_service.configure_tcp_udp_route(
                    name=name,
                    namespace=namespace,
                    protocol=protocol,
                    entry_points=entry_points,
                    routes=routes,
                    tls=tls,
                    dry_run=dry_run,
                )
                return ExecutionResult.model_validate(res)
            except Exception as exc:
                self.handle_error(exc, "traefik_configure_tcp_udp_route", namespace=namespace, resource_name=name)
