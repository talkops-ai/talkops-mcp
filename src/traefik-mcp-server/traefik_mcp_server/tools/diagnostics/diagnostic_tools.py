"""Diagnostic Tools (T11–T15) for the 'diagnostics' toolset."""

from typing import Any, Dict, List, Literal, Optional, Union
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from traefik_mcp_server.models.schemas import (
    AuditReport,
    LogSummary,
    MetricsComparison,
    RouteDiagnosisReport,
    RequestTrace,
)
from traefik_mcp_server.tools.base import BaseTool


class DiagnosticTools(BaseTool):
    """Read-only diagnostic, trace, metrics, log, and audit tools (T11–T15)."""

    def register(self, mcp: FastMCP) -> None:
        if not self.should_register("diagnostics", is_write=False):
            return

        @mcp.tool(
            name="traefik_diagnose_route",
            description=(
                "Perform deep end-to-end health diagnosis of an IngressRoute, IngressRouteTCP, "
                "IngressRouteUDP, TraefikService, Ingress, HTTPRoute, GRPCRoute, TLSRoute, TCPRoute, "
                "or Gateway across Kubernetes manifests, Traefik runtime API, endpoints, and TLS."
            ),
            tags={"diagnostics", "read"},
            annotations=ToolAnnotations(
                title="Diagnose Traefik Route Health",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def traefik_diagnose_route(
            name: str = Field(..., min_length=1, description="Route, TraefikService, Ingress, or Gateway name"),
            kind: Literal[
                "IngressRoute",
                "IngressRouteTCP",
                "IngressRouteUDP",
                "TraefikService",
                "Ingress",
                "HTTPRoute",
                "GRPCRoute",
                "TLSRoute",
                "TCPRoute",
                "Gateway",
            ] = Field(default="IngressRoute", description="Resource kind to diagnose"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            include: Optional[
                List[Literal["runtime", "endpoints", "tls", "metrics", "events"]]
            ] = Field(
                default=None,
                description="Inspection dimensions to include (defaults to runtime, endpoints, tls, events)",
            ),
            detail: Literal["summary", "full"] = Field(
                default="summary",
                description="Output detail level ('summary' or 'full')",
            ),
        ) -> RouteDiagnosisReport:
            try:
                res = await self.traefik_service.diagnose_route(
                    kind=kind,
                    name=name,
                    namespace=namespace,
                    include=include,
                    detail=detail,
                )
                return RouteDiagnosisReport.model_validate(res)
            except Exception as e:
                self.handle_error(e, "traefik_diagnose_route", namespace=namespace, resource_name=name)

        @mcp.tool(
            name="traefik_trace_request",
            description=(
                "Evaluate which Traefik router matches a synthetic HTTP/TCP request by priority, "
                "trace the ordered middleware chain and backend service tree, identify shadowed "
                "routers and near-misses, and optionally run an SSRF-guarded live HTTP/TLS probe."
            ),
            tags={"diagnostics", "read"},
            annotations=ToolAnnotations(
                title="Trace Synthetic Request Through Traefik Routers",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def traefik_trace_request(
            request: Dict[str, Any] = Field(
                ...,
                description="Synthetic request specification (url or host/path/method/headers/query/client_ip/protocol/sni)",
            ),
            entry_point: Optional[str] = Field(
                default=None,
                description="Optional entryPoint filter (e.g. 'websecure')",
            ),
            probe: Optional[Union[bool, Dict[str, Any]]] = Field(
                default=None,
                description="Optional live HTTP/TLS probe options (True or {enabled, method, timeout_seconds, expect_status})",
            ),
            top_n: int = Field(
                default=5,
                ge=1,
                le=25,
                description="Maximum number of shadowed routers and near-misses to return",
            ),
        ) -> RequestTrace:
            try:
                res = await self.traefik_service.trace_request(
                    request=request,
                    entry_point=entry_point,
                    probe=probe,
                    top_n=top_n,
                )
                return RequestTrace.model_validate(res)
            except Exception as e:
                self.handle_error(e, "traefik_trace_request")

        @mcp.tool(
            name="traefik_compare_traffic_metrics",
            description=(
                "Query Prometheus for Traefik service, router, or entrypoint request rate, "
                "4xx/5xx error rate, P50/P95/P99 latency, and open connections across baseline "
                "and comparison windows, or compare canary vs stable backend sub-services."
            ),
            tags={"diagnostics", "read"},
            annotations=ToolAnnotations(
                title="Compare Traefik Prometheus Traffic Metrics",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def traefik_compare_traffic_metrics(
            name: str = Field(..., min_length=1, description="Service, router, or entrypoint name"),
            scope: Literal["service", "router", "entrypoint"] = Field(
                default="service",
                description="Metric aggregation scope",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            baseline_window: str = Field(default="1h", description="Baseline Prometheus window (e.g. '1h')"),
            comparison_window: str = Field(default="15m", description="Comparison Prometheus window (e.g. '15m')"),
            include_backend_split: bool = Field(
                default=True,
                description="If True, also compare canary vs stable weighted backend sub-services",
            ),
        ) -> MetricsComparison:
            try:
                res = await self.traefik_service.compare_traffic_metrics(
                    scope=scope,
                    name=name,
                    namespace=namespace,
                    baseline_window=baseline_window,
                    comparison_window=comparison_window,
                    include_backend_split=include_backend_split,
                )
                return MetricsComparison.model_validate(res)
            except Exception as e:
                self.handle_error(e, "traefik_compare_traffic_metrics", namespace=namespace, resource_name=name)

        @mcp.tool(
            name="traefik_analyze_logs",
            description=(
                "Parse and aggregate Traefik pod access logs (JSON or CLF) or controller logs "
                "with automatic secret/token redaction, status/router/latency filtering, and "
                "grouped counts."
            ),
            tags={"diagnostics", "read"},
            annotations=ToolAnnotations(
                title="Analyze Traefik Access & Controller Logs",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def traefik_analyze_logs(
            source: Literal["access", "controller"] = Field(
                default="access",
                description="Log stream source ('access' or 'controller')",
            ),
            since: str = Field(default="15m", description="Lookback window (e.g. '15m', '1h')"),
            filters: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Optional log filter criteria (router, service, status_range, min_duration_ms, client_ip, path_prefix, level)",
            ),
            group_by: Literal[
                "status", "router", "service", "path_prefix", "client_ip", "error_code"
            ] = Field(
                default="status",
                description="Dimension to group log counts by",
            ),
            limit_samples: int = Field(
                default=5,
                ge=1,
                le=25,
                description="Maximum number of redacted log samples to return",
            ),
        ) -> LogSummary:
            try:
                res = await self.traefik_service.analyze_logs(
                    source=source,
                    since=since,
                    filters=filters,
                    group_by=group_by,
                    limit_samples=limit_samples,
                )
                return LogSummary.model_validate(res)
            except Exception as e:
                self.handle_error(e, "traefik_analyze_logs")

        @mcp.tool(
            name="traefik_audit_configuration",
            description=(
                "Run 20 deterministic security, TLS, reliability, hygiene, v3_migration, and "
                "gateway_api checks across Traefik static configuration, routes, policies, "
                "certificates, and Gateway API objects."
            ),
            tags={"diagnostics", "read"},
            annotations=ToolAnnotations(
                title="Audit Traefik Security & Configuration Posture",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def traefik_audit_configuration(
            namespaces: Optional[List[str]] = Field(
                default=None,
                description="Optional list of namespaces to audit (None = all watched namespaces)",
            ),
            categories: Optional[
                List[
                    Literal[
                        "security",
                        "tls",
                        "reliability",
                        "hygiene",
                        "v3_migration",
                        "gateway_api",
                    ]
                ]
            ] = Field(
                default=None,
                description="Optional subset of audit categories to execute",
            ),
            min_severity: Literal["info", "low", "medium", "high", "critical"] = Field(
                default="low",
                description="Minimum finding severity threshold",
            ),
            max_findings: int = Field(
                default=50,
                ge=1,
                le=500,
                description="Maximum number of findings to return before truncation",
            ),
        ) -> AuditReport:
            try:
                res = await self.traefik_service.audit_configuration(
                    namespaces=namespaces,
                    categories=categories,
                    min_severity=min_severity,
                    max_findings=max_findings,
                )
                return AuditReport.model_validate(res)
            except Exception as e:
                self.handle_error(e, "traefik_audit_configuration")
