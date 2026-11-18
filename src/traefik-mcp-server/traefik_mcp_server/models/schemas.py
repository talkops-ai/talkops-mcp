"""Pydantic input and output models for Traefik MCP Server tools."""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ALL_DIAGNOSIS_CODES: tuple[str, ...] = (
    # Route & Provider
    "HEALTHY",
    "ROUTE_NOT_FOUND",
    "ROUTE_IGNORED_BY_PROVIDER",
    "INGRESS_NOT_CLAIMED",
    "INGRESS_PROVIDER_CONFLICT",
    "LEGACY_API_GROUP",
    "RULE_SYNTAX_V2",
    "RULE_INVALID",
    "ROUTER_NOT_IN_RUNTIME",
    "ROUTER_DISABLED",
    "ENTRYPOINT_UNKNOWN",
    "PRIORITY_SHADOWED",
    # Middlewares
    "MIDDLEWARE_MISSING",
    "MIDDLEWARE_CROSS_NAMESPACE_BLOCKED",
    "MIDDLEWARE_RUNTIME_ERROR",
    "MIDDLEWARE_CHAIN_CYCLE",
    # Backends & Weights
    "BACKEND_SERVICE_MISSING",
    "BACKEND_PORT_MISMATCH",
    "NO_READY_ENDPOINTS",
    "PARTIAL_ENDPOINTS",
    "EXTERNALNAME_NOT_ALLOWED",
    "EMPTY_SERVICE_NOT_ALLOWED",
    "TRAEFIK_SERVICE_MISSING",
    "WEIGHT_TO_EMPTY_BACKEND",
    "ALL_WEIGHTS_ZERO",
    "MIRROR_TARGET_MISSING",
    "SERVERS_TRANSPORT_MISSING",
    "BACKEND_HEALTHCHECK_DOWN",
    # TLS
    "TLS_SECRET_MISSING",
    "TLS_CERT_EXPIRED",
    "TLS_CERT_EXPIRING",
    "TLS_SAN_MISMATCH",
    "TLS_OPTION_MISSING",
    "CERT_RESOLVER_UNKNOWN",
    "TCP_SNI_WITHOUT_TLS",
    # Gateway API
    "GATEWAY_NOT_PROGRAMMED",
    "GATEWAY_LISTENER_REJECTS_ROUTE",
    "GATEWAY_ROUTE_NOT_ACCEPTED",
    "GATEWAY_REFS_UNRESOLVED",
    "REFERENCE_GRANT_MISSING",
    # Traffic & Ownership
    "HIGH_ERROR_RATE",
    "ARGO_ROLLOUT_MANAGED",
    "GITOPS_MANAGED",
)


HTTP_MIDDLEWARE_TYPES = Literal[
    "add_prefix",
    "basic_auth",
    "buffering",
    "chain",
    "circuit_breaker",
    "compress",
    "content_type",
    "digest_auth",
    "errors",
    "forward_auth",
    "grpc_web",
    "headers",
    "ip_allow_list",
    "ip_deny_list",
    "in_flight_req",
    "pass_tls_client_cert",
    "plugin",
    "rate_limit",
    "redirect_regex",
    "redirect_scheme",
    "replace_path",
    "replace_path_regex",
    "retry",
    "strip_prefix",
    "strip_prefix_regex",
]

TCP_MIDDLEWARE_TYPES = Literal[
    "ip_allow_list",
    "in_flight_conn",
]

ALL_MIDDLEWARE_TYPES = Literal[
    "add_prefix",
    "basic_auth",
    "buffering",
    "chain",
    "circuit_breaker",
    "compress",
    "content_type",
    "digest_auth",
    "errors",
    "forward_auth",
    "grpc_web",
    "headers",
    "ip_allow_list",
    "ip_deny_list",
    "in_flight_req",
    "in_flight_conn",
    "pass_tls_client_cert",
    "plugin",
    "rate_limit",
    "redirect_regex",
    "redirect_scheme",
    "replace_path",
    "replace_path_regex",
    "retry",
    "strip_prefix",
    "strip_prefix_regex",
]


class GuardResult(BaseModel):
    """Outcome of a single write-guard check in the execution pipeline."""

    guard: str = Field(description="Guard identifier (e.g. write_access, namespace_policy, ownership, crd_schema, referential_integrity, server_dry_run).")
    passed: bool = Field(description="True when the guard passed without blocking.")
    severity: Literal["info", "warning", "error"] = Field(default="info", description="Severity level.")
    message: str = Field(default="", description="Human- and model-readable explanation.")


class ExecutionResult(BaseModel):
    """Standard concise response returned by mutating and destructive MCP tools."""

    status: Literal[
        "success",
        "preview",
        "confirmation_required",
        "cancelled",
        "aborted",
        "refused",
    ] = Field(description="Execution outcome status.")
    summary: str = Field(description="Concise human- and model-readable outcome summary.")
    dry_run: bool = Field(
        default=False,
        description="True when returned as a dry-run preview without cluster mutation.",
    )
    manifest: Optional[str] = Field(
        default=None,
        description="Rendered YAML manifest or patch preview (sanitized).",
    )
    diff: Optional[str] = Field(
        default=None,
        description="Unified diff against the live Kubernetes object if it already exists.",
    )
    resource_uri: Optional[str] = Field(
        default=None,
        description="MCP Resource URI to inspect the target resource without spending a tool turn.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Operational or safety warnings detected during execution.",
    )
    guards: List[GuardResult] = Field(
        default_factory=list,
        description="Results of the write-guard pipeline checks.",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Compact operation-specific fields.",
    )


class RouteMatch(BaseModel):
    """Structured Traefik v3 HTTP route matching specification."""

    model_config = ConfigDict(extra="allow")

    host: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Hostname(s) matched via Host(`...`).",
    )
    hosts: Optional[List[str]] = Field(
        default=None,
        description="Hostnames matched via Host(`...`), combined with ||.",
    )
    cookies: Optional[Dict[str, str]] = Field(
        default=None,
        description="Exact cookie key/value pairs matched via HeaderRegexp(`Cookie`, ...).",
    )
    path_prefix: Optional[str] = Field(
        default=None,
        description="URL path prefix matched via PathPrefix(`...`).",
    )
    path: Optional[str] = Field(
        default=None,
        description="Exact URL path matched via Path(`...`).",
    )
    path_regexp: Optional[str] = Field(
        default=None,
        description="Regular expression path matched via PathRegexp(`...`).",
    )
    methods: Optional[List[str]] = Field(
        default=None,
        description="HTTP methods matched via Method(`GET`, ...).",
    )
    headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="Exact HTTP request headers matched via Header(`Key`, `Value`).",
    )
    header_regexps: Optional[Dict[str, str]] = Field(
        default=None,
        description="Regex HTTP headers or cookies matched via HeaderRegexp(`Key`, `Pattern`).",
    )
    query: Optional[Dict[str, str]] = Field(
        default=None,
        description="Query parameters matched via Query(`key`, `value`).",
    )
    client_ips: Optional[List[str]] = Field(
        default=None,
        description="Client IP/CIDR blocks matched via ClientIP(`...`).",
    )
    raw: Optional[str] = Field(
        default=None,
        description="Explicit Traefik v3 match rule string (mutually exclusive with structured fields).",
    )


class MiddlewareRef(BaseModel):
    """Reference to a Traefik Middleware or MiddlewareTCP resource."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Middleware resource name.")
    namespace: Optional[str] = Field(
        default=None,
        description="Optional Middleware namespace (requires allowCrossNamespace when different from route namespace).",
    )


class StickyCookie(BaseModel):
    """Traefik sticky-session cookie configuration."""

    model_config = ConfigDict(extra="allow")

    name: Optional[str] = Field(default=None, description="Cookie name (e.g. 'traefik_affinity').")
    secure: bool = Field(default=True, description="Set Secure flag on cookie.")
    http_only: bool = Field(default=True, description="Set HttpOnly flag on cookie.")
    same_site: Optional[Literal["none", "lax", "strict"]] = Field(
        default="lax",
        description="SameSite policy ('none', 'lax', or 'strict').",
    )
    max_age: Optional[int] = Field(default=None, description="Cookie Max-Age in seconds.")
    path: Optional[str] = Field(default=None, description="Cookie URL path.")

    @field_validator("same_site", mode="before")
    @classmethod
    def _normalize_same_site(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class HealthCheck(BaseModel):
    """Active backend healthCheck configuration for Traefik services."""

    model_config = ConfigDict(extra="allow")

    path: str = Field(default="/health", description="Health check endpoint path.")
    interval: str = Field(default="10s", description="Probe interval duration (e.g. '10s').")
    timeout: str = Field(default="3s", description="Probe timeout duration (e.g. '3s').")
    scheme: Optional[Literal["http", "https"]] = Field(default=None, description="Override probe scheme.")
    port: Optional[int] = Field(default=None, description="Override probe port.")
    hostname: Optional[str] = Field(default=None, description="Custom Host header for probe.")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Custom HTTP headers for probe.")
    mode: Optional[Literal["http", "grpc"]] = Field(default=None, description="Health check mode ('http' or 'grpc').")
    follow_redirects: Optional[bool] = Field(default=None, description="Whether to follow HTTP redirects.")


class BackendRef(BaseModel):
    """Backend service reference with Traefik v3 load-balancing, healthCheck, and sticky options."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Kubernetes Service or TraefikService name.")
    port: Optional[Union[int, str]] = Field(
        default=80,
        description="Service port number or named port (required for Kind='Service').",
    )
    kind: Literal["Service", "TraefikService"] = Field(
        default="Service",
        description="Backend target kind ('Service' or 'TraefikService').",
    )
    namespace: Optional[str] = Field(default=None, description="Backend namespace if cross-namespace.")
    weight: Optional[int] = Field(default=None, ge=0, description="Traffic weight (0-100+).")
    scheme: Optional[Literal["http", "https", "h2c"]] = Field(
        default=None,
        description="Backend protocol scheme ('http', 'https', or 'h2c').",
    )
    strategy: Optional[Literal["wrr", "p2c", "hrw", "leasttime", "RoundRobin"]] = Field(
        default=None,
        description="Load-balancing strategy ('wrr', 'p2c', 'hrw', 'leasttime' — schema-gated).",
    )
    pass_host_header: Optional[bool] = Field(
        default=None,
        description="Forward client Host header to backend.",
    )
    servers_transport: Optional[str] = Field(
        default=None,
        description="ServersTransport CRD name for backend TLS/timeout tuning.",
    )
    native_lb: Optional[bool] = Field(
        default=None,
        description="Use Kubernetes Service ClusterIP directly instead of Pod EndpointSlices.",
    )
    sticky: Optional[StickyCookie] = Field(
        default=None,
        description="Sticky-session cookie settings on this backend.",
    )
    health_check: Optional[HealthCheck] = Field(
        default=None,
        description="Active backend health check settings.",
    )
    flush_interval: Optional[str] = Field(
        default=None,
        description="Responseforwarding flushInterval (e.g. '100ms' for streaming/SSE).",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_backend_ref_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for camel, snake in (
            ("passHostHeader", "pass_host_header"),
            ("serversTransport", "servers_transport"),
            ("nativeLB", "native_lb"),
            ("healthCheck", "health_check"),
            ("flushInterval", "flush_interval"),
        ):
            if camel in out and snake not in out:
                out[snake] = out.pop(camel)
        return out


class RouteTLS(BaseModel):
    """TLS configuration for IngressRoute and IngressRouteTCP."""

    model_config = ConfigDict(extra="allow")

    secret_name: Optional[str] = Field(
        default=None,
        description="Kubernetes TLS Secret name containing tls.crt and tls.key.",
    )
    cert_resolver: Optional[str] = Field(
        default=None,
        description="Traefik ACME certResolver name defined in static config.",
    )
    domains: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Domains list [{'main': 'example.com', 'sans': ['*.example.com']}].",
    )
    options: Optional[Dict[str, str]] = Field(
        default=None,
        description="TLSOption reference {'name': 'modern-tls', 'namespace': 'default'}.",
    )
    store: Optional[Dict[str, str]] = Field(
        default=None,
        description="TLSStore reference {'name': 'default', 'namespace': 'default'}.",
    )
    passthrough: bool = Field(
        default=False,
        description="Enable TLS passthrough without termination (IngressRouteTCP only).",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_tls_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "secretName" in out and "secret_name" not in out:
            out["secret_name"] = out.pop("secretName")
        if "certResolver" in out and "cert_resolver" not in out:
            out["cert_resolver"] = out.pop("certResolver")
        if "options_name" in out and "options" not in out:
            opt_n = out.pop("options_name")
            if opt_n:
                opt_dict: Dict[str, str] = {"name": str(opt_n)}
                if out.get("options_namespace"):
                    opt_dict["namespace"] = str(out.pop("options_namespace"))
                out["options"] = opt_dict
        elif isinstance(out.get("options"), str):
            out["options"] = {"name": out["options"]}
        return out


class HttpRouteRule(BaseModel):
    """Single routing rule inside an HTTP IngressRoute."""

    model_config = ConfigDict(extra="allow")

    match: Union[RouteMatch, str] = Field(
        description="Structured RouteMatch or raw Traefik v3 match expression."
    )
    priority: Optional[int] = Field(
        default=None,
        description="Explicit router priority (higher wins).",
    )
    middlewares: List[MiddlewareRef] = Field(
        default_factory=list,
        description="Ordered list of middlewares executed on matching requests.",
    )
    services: List[BackendRef] = Field(
        min_length=1,
        description="One or more backend Services or TraefikServices.",
    )
    observability: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Per-router observability overrides ({'accessLogs': True, 'metrics': True, 'tracing': True}).",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_rule_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "service" in out and "services" not in out:
            svc = out.pop("service")
            out["services"] = [svc] if isinstance(svc, dict) else svc
        if isinstance(out.get("middlewares"), list):
            out["middlewares"] = [
                {"name": m} if isinstance(m, str) else m for m in out["middlewares"]
            ]
        return out


class WeightedExposeConfig(BaseModel):
    """Optional IngressRoute exposure settings when creating a weighted TraefikService."""

    model_config = ConfigDict(extra="allow")

    route_name: Optional[str] = Field(
        default=None,
        description="IngressRoute name to create/update (defaults to TraefikService name without '-wrr').",
    )
    match: Union[RouteMatch, str] = Field(
        description="RouteMatch or Traefik v3 rule string for the exposing IngressRoute."
    )
    entry_points: List[str] = Field(
        default_factory=lambda: ["websecure"],
        description="Traefik entryPoints for the exposing IngressRoute.",
    )
    tls: Optional[RouteTLS] = Field(
        default=None,
        description="Optional TLS configuration for the exposing IngressRoute.",
    )
    middlewares: List[MiddlewareRef] = Field(
        default_factory=list,
        description="Optional middlewares to attach to the exposing IngressRoute.",
    )


class MirrorTarget(BaseModel):
    """Shadow mirror target service specification."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Shadow Kubernetes Service name.")
    port: Union[int, str] = Field(default=80, description="Shadow Service port.")
    percent: int = Field(ge=0, le=100, description="Percentage of traffic mirrored (0-100).")
    namespace: Optional[str] = Field(default=None, description="Optional namespace.")


class MirroringSpec(BaseModel):
    """Specification for TraefikService traffic mirroring."""

    model_config = ConfigDict(extra="allow")

    main: BackendRef = Field(description="Primary production backend Service.")
    mirrors: List[MirrorTarget] = Field(min_length=1, description="Mirror target Services and percentages.")
    mirror_body: bool = Field(default=True, description="Whether to mirror request bodies.")
    max_body_size: Optional[int] = Field(default=None, description="Max request body bytes to mirror.")

    @model_validator(mode="before")
    @classmethod
    def _normalize_mirror_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "main" not in out:
            for alt in ("primary_service", "primary", "service"):
                if alt in out:
                    out["main"] = out.pop(alt)
                    break
        if "mirrorBody" in out and "mirror_body" not in out:
            out["mirror_body"] = out.pop("mirrorBody")
        if "maxBodySize" in out and "max_body_size" not in out:
            out["max_body_size"] = out.pop("maxBodySize")
        return out


class MiddlewarePatchSpec(BaseModel):
    """Ordered middleware chain mutation for traefik_update_route."""

    model_config = ConfigDict(extra="allow")

    action: Literal["attach", "detach", "replace"] = Field(
        default="attach",
        description="How to modify the route's middleware chain ('attach', 'detach', or 'replace').",
    )
    refs: List[MiddlewareRef] = Field(
        default_factory=list,
        description="Middleware references to attach, detach, or replace with.",
    )
    position: Union[Literal["append", "prepend"], int] = Field(
        default="append",
        description="Insertion position for 'attach' ('append', 'prepend', or 0-based index).",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_mw_patch_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if not out.get("refs"):
            for alt in ("items", "middlewares"):
                if alt in out and out[alt] is not None:
                    out["refs"] = out.pop(alt)
                    break
        if isinstance(out.get("refs"), list):
            out["refs"] = [
                {"name": r} if isinstance(r, str) else r for r in out["refs"]
            ]
        return out


class BackendPatchSpec(BaseModel):
    """Backend service option mutation for traefik_update_route."""

    model_config = ConfigDict(extra="allow")

    service_name: Optional[str] = Field(
        default=None,
        description="Target backend Service name (defaults to primary backend on the route).",
    )
    sticky: Optional[StickyCookie] = Field(default=None, description="Sticky-session cookie settings.")
    health_check: Optional[HealthCheck] = Field(default=None, description="Backend healthCheck settings.")
    strategy: Optional[Literal["wrr", "p2c", "hrw", "leasttime", "RoundRobin"]] = Field(default=None, description="Load balancing strategy.")
    pass_host_header: Optional[bool] = Field(default=None, description="Pass client Host header.")
    servers_transport: Optional[str] = Field(default=None, description="ServersTransport name.")
    native_lb: Optional[bool] = Field(default=None, description="Use native Kubernetes Service load-balancing.")
    scheme: Optional[Literal["http", "https", "h2c"]] = Field(default=None, description="Backend scheme.")
    port: Optional[Union[int, str]] = Field(default=None, description="Updated backend Service port.")

    @model_validator(mode="before")
    @classmethod
    def _normalize_backend_patch_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for camel, snake in (
            ("serviceName", "service_name"),
            ("name", "service_name"),
            ("passHostHeader", "pass_host_header"),
            ("serversTransport", "servers_transport"),
            ("nativeLB", "native_lb"),
            ("healthCheck", "health_check"),
        ):
            if camel in out and snake not in out:
                out[snake] = out.pop(camel)
        return out


class RouteChanges(BaseModel):
    """Patch specification for traefik_update_route."""

    model_config = ConfigDict(extra="allow")

    middlewares: Optional[MiddlewarePatchSpec] = Field(
        default=None,
        description="Ordered middleware chain modifications.",
    )
    tls: Optional[Dict[str, Any]] = Field(
        default=None,
        description="TLS update: {'set': RouteTLS} or {'remove': True}.",
    )
    entry_points: Optional[List[str]] = Field(
        default=None,
        description="Replace route entryPoints list.",
    )
    priority: Optional[int] = Field(
        default=None,
        description="Set router priority on target rule(s).",
    )
    match: Optional[str] = Field(
        default=None,
        description="Update router match expression on target rule(s).",
    )
    ingress_class: Optional[str] = Field(
        default=None,
        description="Set or clear ('') kubernetes.io/ingress.class annotation (or spec.ingressClassName on Ingress).",
    )
    annotations: Optional[Dict[str, Optional[str]]] = Field(
        default=None,
        description="Annotations to set or remove (value None removes key) on the route metadata.",
    )
    backend: Optional[BackendPatchSpec] = Field(
        default=None,
        description="Update backend load-balancing/sticky/transport options.",
    )
    rule_index: Optional[int] = Field(
        default=None,
        description="0-based rule index to patch (None applies to all rules).",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_route_changes_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for camel, snake in (
            ("entryPoints", "entry_points"),
            ("ingressClass", "ingress_class"),
            ("ingressClassName", "ingress_class"),
            ("ruleIndex", "rule_index"),
        ):
            if camel in out and snake not in out:
                out[snake] = out.pop(camel)
        return out


class TcpUdpServiceRef(BaseModel):
    """Backend Service reference for TCP or UDP routing."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Backend Kubernetes Service name.")
    port: Union[int, str] = Field(default=80, description="Backend TCP/UDP port.")
    weight: Optional[int] = Field(default=None, ge=0, description="Optional traffic weight.")
    proxy_protocol_version: Optional[Literal[1, 2]] = Field(
        default=None,
        description="PROXY protocol version (1 or 2, TCP only).",
    )
    servers_transport: Optional[str] = Field(
        default=None,
        description="ServersTransportTCP name (TCP only).",
    )
    native_lb: Optional[bool] = Field(default=None, description="Use nativeLB.")


class TcpUdpRouteRule(BaseModel):
    """Single rule for IngressRouteTCP or IngressRouteUDP."""

    model_config = ConfigDict(extra="allow")

    match: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="TCP match rule (e.g. 'HostSNI(`db.example.com`)' or {'sni': ['db.example.com'], 'client_ips': []}). Omit for UDP.",
    )
    priority: Optional[int] = Field(default=None, description="Router priority (TCP only).")
    middlewares: List[MiddlewareRef] = Field(
        default_factory=list,
        description="Ordered MiddlewareTCP references (TCP only).",
    )
    services: List[TcpUdpServiceRef] = Field(
        min_length=1,
        description="Backend TCP/UDP services.",
    )


class DiagnosisCodeItem(BaseModel):
    """Detailed diagnosis finding entry."""

    code: str = Field(description="Deterministic diagnosis code.")
    severity: Literal["info", "warning", "error", "critical"] = Field(default="error")
    evidence: str = Field(default="", description="Concrete cluster/runtime evidence.")
    remediation: str = Field(default="", description="Actionable fix recommendation.")
    resource_uri: Optional[str] = Field(default=None, description="Related traefik:// resource URI.")


class RouteDiagnosisReport(BaseModel):
    """Comprehensive N-to-1 route diagnosis report returned by traefik_diagnose_route."""

    kind: str = Field(default="IngressRoute", description="Diagnosed route resource kind.")
    name: str = Field(description="Route name.")
    namespace: str = Field(default="default", description="Kubernetes namespace.")
    healthy: bool = Field(description="True when route and all dependencies are healthy.")
    verdict: str = Field(description="Concise human- and model-readable diagnosis summary.")
    diagnosis_codes: List[str] = Field(
        default_factory=list,
        description="Deterministic machine-readable diagnosis codes.",
    )
    diagnosis_items: List[DiagnosisCodeItem] = Field(
        default_factory=list,
        description="Structured findings with evidence, remediation, and resource URIs.",
    )
    runtime_router: Dict[str, Any] = Field(
        default_factory=dict,
        description="Traefik runtime router status and error message.",
    )
    backends: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Backend Services, ready/total endpoints, weights, and runtime server status.",
    )
    middlewares: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Attached middlewares, existence status, and runtime errors.",
    )
    tls: Dict[str, Any] = Field(
        default_factory=dict,
        description="TLS Secret, SAN coverage, and certificate expiry details.",
    )
    metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional Prometheus RPS and error rate summary.",
    )
    warning_events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Recent Kubernetes Warning events for the route.",
    )
    next_actions: List[str] = Field(
        default_factory=list,
        description="Recommended next tool or resource actions.",
    )


class TraceRequestSpec(BaseModel):
    """Simulated request specification for traefik_trace_request."""

    model_config = ConfigDict(extra="allow")

    url: Optional[str] = Field(default=None, description="Full URL (e.g. 'https://api.example.com/v1/users').")
    host: Optional[str] = Field(default=None, description="Request Host header (if url not provided).")
    path: str = Field(default="/", description="Request URL path.")
    method: str = Field(default="GET", description="HTTP method.")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Request headers (redacted in output).")
    query: Optional[Dict[str, str]] = Field(default=None, description="Query parameters.")
    client_ip: Optional[str] = Field(default=None, description="Simulated client IP address.")
    sni: Optional[str] = Field(default=None, description="TLS SNI hostname.")
    protocol: Literal["http", "tcp"] = Field(default="http", description="Protocol ('http' or 'tcp').")


class ProbeOptions(BaseModel):
    """Live HTTP/TLS endpoint probe options for traefik_trace_request."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False, description="Set True to perform a live HTTP/TLS check.")
    method: Literal["GET", "HEAD"] = Field(default="HEAD", description="HTTP probe method.")
    resolve_via: Literal["dns", "traefik_lb"] = Field(
        default="dns",
        description="Connect via normal DNS or directly to the Traefik LoadBalancer IP with Host/SNI.",
    )
    expect_status: Optional[List[int]] = Field(default=None, description="Expected HTTP status codes.")
    timeout_seconds: int = Field(default=5, ge=1, le=30, description="Probe timeout in seconds.")


class RequestTrace(BaseModel):
    """Response returned by traefik_trace_request."""

    matched: bool = Field(description="True when at least one active router matched the request.")
    summary: str = Field(description="Concise explanation of the routing trace and optional live probe.")
    matched_router: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Winning router details (name, rule, priority, entryPoints, provider).",
    )
    source_resource_uri: Optional[str] = Field(
        default=None,
        description="MCP Resource URI for the winning route manifest.",
    )
    middleware_chain: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Ordered middleware chain executed on the matched router.",
    )
    service_tree: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Resolved backend service tree with weights and server status.",
    )
    shadowed_routers: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Lower-priority routers that also matched the request but were shadowed.",
    )
    near_misses: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Routers that partially matched (e.g. Host matched, PathPrefix failed).",
    )
    probe_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Live HTTP/TLS probe outcome when probe.enabled=True.",
    )


class MetricsComparison(BaseModel):
    """Response returned by traefik_compare_traffic_metrics."""

    model_config = ConfigDict(extra="allow")

    scope: Literal["service", "router", "entrypoint"] = Field(default="service")
    name: str = Field(description="Target service, router, or entrypoint name.")
    namespace: Optional[str] = Field(default="default")
    baseline_window: str = Field(default="1h")
    comparison_window: str = Field(default="15m")
    prometheus_available: bool = Field(
        default=True,
        description="True when Prometheus was reachable and returned metric series.",
    )
    verdict: Literal["regression", "stable", "improved", "insufficient_data"] = Field(
        description="Automated traffic comparison verdict."
    )
    summary: str = Field(description="Concise delta summary.")
    baseline: Dict[str, Any] = Field(default_factory=dict)
    comparison: Dict[str, Any] = Field(default_factory=dict)
    deltas: Dict[str, Any] = Field(default_factory=dict)
    backend_split: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Configured vs observed traffic split across weighted backends.",
    )


class LogFilterSpec(BaseModel):
    """Filter criteria for traefik_analyze_logs."""

    model_config = ConfigDict(extra="allow")

    router: Optional[str] = Field(default=None, description="Filter by Traefik router name substring.")
    service: Optional[str] = Field(default=None, description="Filter by Traefik service name substring.")
    host: Optional[str] = Field(default=None, description="Filter by RequestHost.")
    path_prefix: Optional[str] = Field(default=None, description="Filter by RequestPath prefix.")
    status_class: Optional[Literal["2xx", "3xx", "4xx", "5xx"]] = Field(
        default=None,
        description="Filter by HTTP status code class.",
    )
    status_codes: Optional[List[int]] = Field(default=None, description="Filter by specific HTTP status codes.")
    client_ip: Optional[str] = Field(default=None, description="Filter by ClientHost IP.")
    min_duration_ms: Optional[float] = Field(default=None, description="Minimum request duration in milliseconds.")


class LogSummary(BaseModel):
    """Response returned by traefik_analyze_logs."""

    model_config = ConfigDict(extra="allow")

    source: Literal["access", "controller"] = Field(default="access")
    since: str = Field(default="15m")
    group_by: str = Field(default="status")
    total_lines_scanned: int = Field(default=0)
    matched_lines: int = Field(default=0)
    summary: str = Field(default="")
    groups: List[Dict[str, Any]] = Field(default_factory=list)
    top_aggregates: List[Dict[str, Any]] = Field(default_factory=list)
    samples: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Redacted log sample entries.",
    )


class AuditFinding(BaseModel):
    """Single security, TLS, reliability, hygiene, or v3 migration finding."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Deterministic audit check ID.")
    check_id: Optional[str] = Field(default=None, description="Alias for deterministic audit check ID.")
    severity: Literal["low", "medium", "high", "critical"] = Field(description="Finding severity.")
    category: Literal[
        "security",
        "tls",
        "reliability",
        "hygiene",
        "v3_migration",
        "gateway_api",
    ] = Field(description="Audit category.")
    title: str = Field(description="Short finding title.")
    evidence: str = Field(description="Concrete configuration evidence.")
    resource_uri: Optional[str] = Field(default=None, description="Related traefik:// resource URI.")
    remediation_tool: Optional[str] = Field(default=None, description="MCP tool to remediate the finding.")
    skill_reference: Optional[str] = Field(default=None, description="Skill reference path for detailed guidance.")


class AuditReport(BaseModel):
    """Response returned by traefik_audit_configuration."""

    model_config = ConfigDict(extra="allow")

    score: int = Field(ge=0, le=100, description="Overall posture score (0-100).")
    summary: str = Field(description="Concise posture summary.")
    counts: Dict[str, int] = Field(default_factory=dict, description="Finding counts by severity.")
    counts_by_severity: Dict[str, int] = Field(default_factory=dict, description="Finding counts by severity.")
    findings: List[AuditFinding] = Field(default_factory=list, description="Prioritized audit findings.")
