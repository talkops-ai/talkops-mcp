"""NGINX annotation compatibility analyzer.

Maps each nginx.ingress.kubernetes.io/* annotation to a Traefik or Gateway API
equivalent with status (supported | partial | unsupported), target resource hint,
and human-readable notes.

Ported from ing-switch pkg/analyzer (MIT license).
Reference: docs/ing-switch/pkg/analyzer/{compatibility.go, report.go, annotations.go}
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from traefik_mcp_server.migration_nginx.scanner import IngressInfo, ScanResult



# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class AnnotationMapping:
    original_key: str
    original_value: str
    status: str  # "supported" | "partial" | "unsupported"
    target_resource: str = ""
    note: str = ""
    category: str = ""


@dataclass
class IngressReport:
    namespace: str = ""
    name: str = ""
    mappings: List[AnnotationMapping] = field(default_factory=list)
    overall_status: str = "ready"  # "ready" | "workaround" | "breaking"


@dataclass
class Summary:
    total: int = 0
    fully_compatible: int = 0
    needs_workaround: int = 0
    has_unsupported: int = 0


@dataclass
class AnalysisReport:
    target: str = "traefik"
    ingress_reports: List[IngressReport] = field(default_factory=list)
    summary: Summary = field(default_factory=Summary)


# ── Annotation category lookup ─────────────────────────────────────────────────

ANNOTATION_CATEGORIES: Dict[str, str] = {
    # TLS / Redirect
    "ssl-redirect": "tls", "force-ssl-redirect": "tls", "ssl-passthrough": "tls",
    "ssl-ciphers": "tls", "auth-tls-secret": "tls", "auth-tls-verify-client": "tls",
    # Authentication
    "auth-url": "auth", "auth-method": "auth", "auth-response-headers": "auth",
    "auth-request-redirect": "auth", "auth-type": "auth", "auth-secret": "auth",
    "auth-realm": "auth",
    # Routing
    "rewrite-target": "routing", "use-regex": "routing", "app-root": "routing",
    "permanent-redirect": "routing", "temporal-redirect": "routing",
    "server-snippet": "routing", "configuration-snippet": "routing",
    # Session / Affinity
    "affinity": "affinity", "affinity-mode": "affinity",
    "session-cookie-name": "affinity", "session-cookie-path": "affinity",
    "session-cookie-samesite": "affinity", "session-cookie-secure": "affinity",
    "session-cookie-conditional-samesite-none": "affinity",
    "session-cookie-expires": "affinity", "session-cookie-max-age": "affinity",
    "session-cookie-change-on-failure": "affinity",
    # Rate Limiting
    "limit-rps": "ratelimit", "limit-rpm": "ratelimit",
    "limit-connections": "ratelimit", "limit-burst-multiplier": "ratelimit",
    "limit-whitelist": "ratelimit",
    # Proxy / Timeouts
    "proxy-body-size": "proxy", "proxy-read-timeout": "proxy",
    "proxy-send-timeout": "proxy", "proxy-connect-timeout": "proxy",
    "proxy-buffering": "proxy", "proxy-request-buffering": "proxy",
    "client-body-buffer-size": "proxy", "proxy-http-version": "proxy",
    # CORS
    "enable-cors": "cors", "cors-allow-origin": "cors",
    "cors-allow-methods": "cors", "cors-allow-headers": "cors",
    "cors-expose-headers": "cors", "cors-allow-credentials": "cors",
    "cors-max-age": "cors",
    # Headers / Access
    "custom-headers": "headers",
    "whitelist-source-range": "access", "denylist-source-range": "access",
    # Canary
    "canary": "canary", "canary-weight": "canary", "canary-weight-total": "canary",
    "canary-by-header": "canary", "canary-by-header-value": "canary",
    "canary-by-cookie": "canary",
    # Protocol
    "websocket-services": "protocol", "grpc-backend": "protocol",
    "backend-protocol": "protocol",
    # Load balancing
    "upstream-hash-by": "lb", "load-balance": "lb",
    # Other
    "service-upstream": "other", "from-to-www-redirect": "other",
    "upstream-vhost": "other", "secure-verify-ca-secret": "other",
}


# ── Traefik mapping table ─────────────────────────────────────────────────────
# key → (status, target_resource, note)

TRAEFIK_MAPPINGS: Dict[str, tuple] = {
    "ssl-redirect":             ("supported",   "Middleware (RedirectScheme)", "Generates RedirectScheme middleware"),
    "force-ssl-redirect":       ("supported",   "Middleware (RedirectScheme)", "Permanent redirect to HTTPS"),
    "enable-cors":              ("supported",   "Middleware (Headers)", "Generates CORS Headers middleware"),
    "cors-allow-origin":        ("supported",   "Middleware (Headers)", "Part of Headers CORS middleware"),
    "cors-allow-methods":       ("supported",   "Middleware (Headers)", "Part of Headers CORS middleware"),
    "cors-allow-headers":       ("supported",   "Middleware (Headers)", "Part of Headers CORS middleware"),
    "cors-expose-headers":      ("supported",   "Middleware (Headers)", "Part of Headers CORS middleware"),
    "cors-allow-credentials":   ("supported",   "Middleware (Headers)", "Part of Headers CORS middleware"),
    "cors-max-age":             ("supported",   "Middleware (Headers)", "Part of Headers CORS middleware"),
    "affinity":                 ("supported",   "Service sticky annotation", "Traefik sticky cookie on Service"),
    "session-cookie-name":      ("supported",   "Service sticky annotation", "Cookie name for session affinity"),
    "session-cookie-path":      ("partial",     "Service sticky annotation", "Limited path support"),
    "session-cookie-samesite":  ("supported",   "Service sticky annotation", "SameSite attribute"),
    "session-cookie-secure":    ("supported",   "Service sticky annotation", "Secure flag"),
    "limit-rps":                ("supported",   "Middleware (RateLimit)", "Generates RateLimit middleware"),
    "limit-rpm":                ("supported",   "Middleware (RateLimit)", "Converted to average rate"),
    "limit-connections":        ("supported",   "Middleware (InFlightReq)", "Max concurrent requests"),
    "limit-burst-multiplier":   ("supported",   "Middleware (RateLimit)", "Burst size multiplier"),
    "limit-whitelist":          ("supported",   "Middleware (RateLimit)", "Exempt IPs from rate limiting"),
    "auth-url":                 ("supported",   "Middleware (ForwardAuth)", "Generates ForwardAuth middleware"),
    "auth-method":              ("partial",     "Middleware (ForwardAuth)", "Only GET/POST supported"),
    "auth-response-headers":    ("supported",   "Middleware (ForwardAuth)", "Headers passed after auth"),
    "auth-request-redirect":    ("partial",     "Middleware (ForwardAuth)", "Redirect URL for auth failure"),
    "auth-type":                ("partial",     "Middleware (BasicAuth)", "Basic auth only; digest not supported"),
    "auth-secret":              ("partial",     "Middleware (BasicAuth)", "Secret format differs from NGINX"),
    "auth-realm":               ("supported",   "Middleware (BasicAuth)", "Auth realm"),
    "whitelist-source-range":   ("supported",   "Middleware (IPAllowList)", "Generates IPAllowList middleware"),
    "denylist-source-range":    ("supported",   "Middleware (IPDenyList)", "Generates IPDenyList middleware"),
    "custom-headers":           ("partial",     "Middleware (Headers)", "ConfigMap ref not supported; inline headers needed"),
    "rewrite-target":           ("supported",   "Middleware (ReplacePath/AddPrefix)", "URL rewrite middleware"),
    "use-regex":                ("supported",   "Router (native)", "Traefik supports regex routing natively"),
    "app-root":                 ("supported",   "Router + Middleware", "Redirect root path"),
    "permanent-redirect":       ("supported",   "Middleware (RedirectRegex)", "Permanent redirect"),
    "temporal-redirect":        ("supported",   "Middleware (RedirectRegex)", "Temporary redirect"),
    "canary":                   ("supported",   "Weighted Services", "Weighted backend traffic splitting"),
    "canary-weight":            ("supported",   "Weighted Services", "Traffic weight percentage"),
    "canary-by-header":         ("partial",     "Router rules", "Header matching in router rules"),
    "canary-by-header-value":   ("partial",     "Router rules", "Header value matching"),
    "canary-by-cookie":         ("partial",     "Router rules", "Cookie-based routing via rules"),
    "proxy-read-timeout":       ("partial",     "ServersTransport CRD", "Requires ServersTransport resource"),
    "proxy-send-timeout":       ("partial",     "ServersTransport CRD", "Requires ServersTransport resource"),
    "proxy-connect-timeout":    ("partial",     "ServersTransport CRD", "Requires ServersTransport resource"),
    "proxy-buffering":          ("unsupported", "", "No direct Traefik equivalent"),
    "proxy-body-size":          ("partial",     "Middleware (Buffering)", "Traefik Buffering middleware with maxRequestBodyBytes"),
    "proxy-request-buffering":  ("partial",     "Native (off by default)", "Off is default behavior; enabling request buffering requires Buffering middleware"),
    "client-body-buffer-size":  ("unsupported", "", "No Traefik equivalent"),
    "configuration-snippet":    ("unsupported", "", "NGINX-specific; intentionally not supported"),
    "server-snippet":           ("unsupported", "", "NGINX-specific; intentionally not supported"),
    "ssl-passthrough":          ("partial",     "Traefik TCP router", "Requires TCP entrypoint config"),
    "backend-protocol":         ("partial",     "Service annotation", "HTTPS/GRPC backends need ServersTransport"),
    "websocket-services":       ("supported",   "Native", "Traefik supports WebSocket natively"),
    "grpc-backend":             ("partial",     "ServersTransport + h2c", "gRPC requires h2c configuration"),
    "upstream-hash-by":         ("unsupported", "", "Hash-based LB not supported in Traefik Ingress"),
    "load-balance":             ("unsupported", "", "Traefik uses round-robin; custom LB not via Ingress"),
    "affinity-mode":            ("partial",     "Service (sticky cookie)", "Traefik always uses persistent affinity; balanced re-balancing is not available"),
    "canary-weight-total":      ("supported",   "Weighted Services", "Traefik uses relative weights; total is implicit"),
    "proxy-http-version":       ("partial",     "ServersTransport CRD", "HTTP/2 via ServersTransport; HTTP/1.0 not supported"),
    "session-cookie-expires":   ("partial",     "Service (sticky cookie maxage)", "Convert seconds to service.sticky.cookie.maxage annotation on Service"),
    "session-cookie-max-age":   ("supported",   "Service (sticky cookie maxage)", "Maps to service.sticky.cookie.maxage annotation on Service"),
    "session-cookie-conditional-samesite-none": ("unsupported", "", "Traefik sets SameSite statically — no UA-conditional logic"),
    "session-cookie-change-on-failure":         ("unsupported", "", "No Traefik equivalent (traefik/traefik#1299)"),
    "service-upstream":         ("supported",   "Service annotation (nativelb)", "Set traefik.ingress.kubernetes.io/service.nativelb: 'true' on Service"),
    "from-to-www-redirect":     ("partial",     "Middleware (RedirectRegex)", "Requires RedirectRegex middleware + separate Ingress entry for www"),
    "upstream-vhost":           ("partial",     "Middleware (Headers) + passhostheader", "Headers middleware sets Host header; disable passhostheader on Service"),
    "secure-verify-ca-secret":  ("partial",     "ServersTransport (rootCAs)", "ServersTransport CRD referencing the CA secret"),
}


# ── Gateway API mapping table ─────────────────────────────────────────────────

GATEWAY_API_MAPPINGS: Dict[str, tuple] = {
    "ssl-redirect":             ("supported",   "HTTPRoute (RequestRedirect filter)", "RequestRedirect filter with scheme=https"),
    "force-ssl-redirect":       ("supported",   "HTTPRoute (RequestRedirect filter)", "301 redirect to HTTPS"),
    "rewrite-target":           ("supported",   "HTTPRoute (URLRewrite filter)", "Path rewrite via URLRewrite filter"),
    "custom-headers":           ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Only upstream-vhost mapped; arbitrary custom-headers require manual ResponseHeaderModifier"),
    "canary":                   ("supported",   "HTTPRoute (weighted backendRefs)", "Traffic split via backendRefs weights"),
    "canary-weight":            ("supported",   "HTTPRoute (weighted backendRefs)", "Weight value in backendRefs"),
    "enable-cors":              ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Manual CORS headers; no native CORS filter in v1"),
    "cors-allow-origin":        ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Set Access-Control-Allow-Origin header"),
    "cors-allow-methods":       ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Set Access-Control-Allow-Methods header"),
    "cors-allow-headers":       ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Set Access-Control-Allow-Headers header"),
    "cors-allow-credentials":   ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Set Access-Control-Allow-Credentials header"),
    "cors-expose-headers":      ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Set Access-Control-Expose-Headers header"),
    "cors-max-age":             ("partial",     "HTTPRoute (ResponseHeaderModifier)", "Set Access-Control-Max-Age header"),
    "auth-url":                 ("partial",     "SecurityPolicy (ExtensionRef)", "Report-only: requires manual Envoy Gateway SecurityPolicy with ext-auth"),
    "auth-response-headers":    ("partial",     "SecurityPolicy (ExtensionRef)", "Report-only: part of SecurityPolicy ext-auth config (not auto-generated)"),
    "limit-rps":                ("partial",     "BackendTrafficPolicy (RateLimit)", "Report-only: requires manual Envoy Gateway BackendTrafficPolicy"),
    "limit-rpm":                ("partial",     "BackendTrafficPolicy (RateLimit)", "Report-only: requires manual rate limit policy"),
    "limit-connections":        ("partial",     "BackendTrafficPolicy (CircuitBreaker)", "Report-only: requires manual circuit breaker policy"),
    "limit-burst-multiplier":   ("partial",     "BackendTrafficPolicy (RateLimit)", "Report-only: burst uses tokens, not a multiplier"),
    "limit-whitelist":          ("unsupported", "", "Per-IP rate limit exemption list is not in BackendTrafficPolicy spec"),
    "whitelist-source-range":   ("partial",     "HTTPRoute (source IP match)", "HTTPRouteMatch with client IP — limited support"),
    "denylist-source-range":    ("partial",     "SecurityPolicy (IPFilter)", "Envoy Gateway SecurityPolicy IP filter"),
    "affinity":                 ("partial",     "BackendLBPolicy (SessionPersistence)", "Gateway API v1.1 SessionPersistence"),
    "session-cookie-name":      ("partial",     "BackendLBPolicy", "Cookie name in SessionPersistence"),
    "proxy-read-timeout":       ("partial",     "HTTPRoute (timeouts)", "HTTPRoute spec.rules[].timeouts.backendRequest"),
    "proxy-connect-timeout":    ("partial",     "HTTPRoute (timeouts)", "HTTPRoute spec.rules[].timeouts.request"),
    "canary-by-header":         ("supported",   "HTTPRoute (header match)", "Match header in HTTPRouteMatch"),
    "canary-by-header-value":   ("supported",   "HTTPRoute (header match)", "Exact header value match"),
    "canary-weight-total":      ("supported",   "HTTPRoute (weighted backendRefs)", "Gateway API backendRefs weights are relative; total is implicit"),
    "use-regex":                ("supported",   "HTTPRoute (PathMatch RegularExpression)", "Native regex path matching"),
    "permanent-redirect":       ("supported",   "HTTPRoute (RequestRedirect)", "301 redirect filter"),
    "temporal-redirect":        ("supported",   "HTTPRoute (RequestRedirect)", "302 redirect filter"),
    "backend-protocol":         ("partial",     "Gateway TLS config", "TLS backend via Gateway listener config"),
    "websocket-services":       ("supported",   "Native", "Gateway API supports WebSocket natively"),
    "grpc-backend":             ("partial",     "GRPCRoute", "Report-only: GRPCRoute generation not implemented; use HTTPRoute with gRPC backend-protocol"),
    "proxy-body-size":          ("partial",     "BackendTrafficPolicy (requestBuffer)", "Envoy Gateway BackendTrafficPolicy with requestBuffer.limit"),
    "proxy-request-buffering":  ("supported",   "Native", "Envoy Gateway streams requests by default"),
    "proxy-http-version":       ("supported",   "Native", "Envoy Gateway handles HTTP/2 and HTTP/1.1 natively"),
    "configuration-snippet":    ("unsupported", "", "NGINX-specific; no equivalent"),
    "server-snippet":           ("unsupported", "", "NGINX-specific; no equivalent"),
    "auth-type":                ("unsupported", "", "No basic auth in core Gateway API"),
    "auth-secret":              ("unsupported", "", "No basic auth in core Gateway API"),
    "ssl-passthrough":          ("partial",     "TLSRoute", "TLS passthrough via TLSRoute"),
    "load-balance":             ("unsupported", "", "Not configurable via Gateway API"),
    "upstream-hash-by":         ("unsupported", "", "Not in core Gateway API"),
    "affinity-mode":            ("partial",     "BackendLBPolicy (SessionPersistence)", "Cookie persistence; balanced re-balancing unavailable"),
    "session-cookie-expires":   ("partial",     "BackendLBPolicy (absoluteTimeout)", "cookieConfig.lifetimeType: Permanent + absoluteTimeout"),
    "session-cookie-max-age":   ("partial",     "BackendLBPolicy (absoluteTimeout)", "cookieConfig.absoluteTimeout field"),
    "session-cookie-conditional-samesite-none": ("unsupported", "", "No Gateway API or Envoy Gateway equivalent"),
    "session-cookie-change-on-failure":         ("unsupported", "", "No Gateway API equivalent"),
    "session-cookie-samesite":  ("unsupported", "", "SameSite not configurable in BackendLBPolicy"),
    "session-cookie-path":      ("unsupported", "", "Cookie path scoping not in BackendLBPolicy spec"),
    "session-cookie-secure":    ("unsupported", "", "Secure flag not configurable in BackendLBPolicy"),
    "proxy-send-timeout":       ("unsupported", "", "No Gateway API equivalent"),
    "proxy-buffering":          ("unsupported", "", "No Gateway API or Envoy Gateway equivalent"),
    "canary-by-cookie":         ("unsupported", "", "Cookie-based canary routing requires ExtensionRef"),
    "app-root":                 ("partial",     "HTTPRoute (URLRewrite)", "URLRewrite on root path; limited to exact path"),
    "service-upstream":         ("supported",   "Native", "Gateway API routes to pod IPs natively"),
    "from-to-www-redirect":     ("supported",   "HTTPRoute (RequestRedirect)", "RequestRedirect filter with hostname replacement"),
    "upstream-vhost":           ("supported",   "HTTPRoute (RequestHeaderModifier)", "RequestHeaderModifier sets Host header"),
    "secure-verify-ca-secret":  ("partial",     "BackendTLSPolicy", "BackendTLSPolicy with caCertificateRefs"),
}


# ── Analyzer ───────────────────────────────────────────────────────────────────

class NginxMigrationAnalyzer:
    """Analyzes NGINX annotations against a target controller's compatibility."""

    def __init__(self, target: str = "traefik"):
        if target not in ("traefik", "gateway-api"):
            raise ValueError(f"Unknown target: {target}. Use 'traefik' or 'gateway-api'.")
        self.target = target
        self._mappings = TRAEFIK_MAPPINGS if target == "traefik" else GATEWAY_API_MAPPINGS

    def analyze(self, scan_result: ScanResult) -> AnalysisReport:
        """Analyze all ingresses in the scan result."""
        report = AnalysisReport(target=self.target)

        for ing in scan_result.ingresses:
            ir = self._analyze_ingress(ing)
            report.ingress_reports.append(ir)

            report.summary.total += 1
            if ir.overall_status == "ready":
                report.summary.fully_compatible += 1
            elif ir.overall_status == "workaround":
                report.summary.needs_workaround += 1
            else:
                report.summary.has_unsupported += 1

        return report

    def _analyze_ingress(self, ing: IngressInfo) -> IngressReport:
        """Analyze a single Ingress's nginx annotations."""
        ir = IngressReport(namespace=ing.namespace, name=ing.name)

        has_unsupported = False
        has_partial = False

        for key, value in sorted(ing.nginx_annotations.items()):
            mapping = self._map_annotation(key, value)
            ir.mappings.append(mapping)

            if mapping.status == "unsupported":
                has_unsupported = True
            elif mapping.status == "partial":
                has_partial = True

        if has_unsupported:
            ir.overall_status = "breaking"
        elif has_partial:
            ir.overall_status = "workaround"
        else:
            ir.overall_status = "ready"

        return ir

    def _map_annotation(self, key: str, value: str) -> AnnotationMapping:
        """Map a single annotation key to the target's equivalent."""
        category = ANNOTATION_CATEGORIES.get(key, "other")

        if key in self._mappings:
            status, target_resource, note = self._mappings[key]
            return AnnotationMapping(
                original_key=key,
                original_value=value,
                status=status,
                target_resource=target_resource,
                note=note,
                category=category,
            )

        return AnnotationMapping(
            original_key=key,
            original_value=value,
            status="unsupported",
            target_resource="",
            note="Unknown annotation — manual review required",
            category=category,
        )


# ── Serialization helpers ──────────────────────────────────────────────────────

def _annotation_mapping_to_dict(m: AnnotationMapping) -> Dict[str, Any]:
    return {
        "originalKey": m.original_key,
        "originalValue": m.original_value,
        "status": m.status,
        "targetResource": m.target_resource,
        "note": m.note,
        "category": m.category,
    }


def analysis_report_to_dict(report: AnalysisReport) -> Dict[str, Any]:
    """Convert AnalysisReport to a JSON-serializable dict.

    For ingresses with ``overallStatus == "breaking"``, includes
    ``breakingAnnotations``: mappings with ``status == "unsupported"`` so
    callers need not scan the full ``mappings`` list.
    """
    ingress_reports: List[Dict[str, Any]] = []
    for ir in report.ingress_reports:
        entry: Dict[str, Any] = {
            "namespace": ir.namespace,
            "name": ir.name,
            "mappings": [_annotation_mapping_to_dict(m) for m in ir.mappings],
            "overallStatus": ir.overall_status,
        }
        if ir.overall_status == "breaking":
            entry["breakingAnnotations"] = [
                _annotation_mapping_to_dict(m)
                for m in ir.mappings
                if m.status == "unsupported"
            ]
        ingress_reports.append(entry)

    return {
        "target": report.target,
        "ingressReports": ingress_reports,
        "summary": {
            "total": report.summary.total,
            "fullyCompatible": report.summary.fully_compatible,
            "needsWorkaround": report.summary.needs_workaround,
            "hasUnsupported": report.summary.has_unsupported,
        },
    }
