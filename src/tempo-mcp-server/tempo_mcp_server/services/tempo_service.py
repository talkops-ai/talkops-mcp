"""Tempo HTTP API service.

Core async HTTP client wrapping all Tempo backend APIs.
Handles multi-tenant header injection, LLM format negotiation,
connection pooling, and response normalization.

Tempo HTTP API mapping (research-validated):
  check_health()            → GET /ready
  get_build_info()          → GET /api/status/buildinfo
  get_status_services()     → GET /status/services
  get_status_endpoints()    → GET /status/endpoints
  get_status_config()       → GET /status/config
  get_attribute_names()     → GET /api/v2/search/tags
  get_attribute_values()    → GET /api/v2/search/tag/{tag}/values
  traceql_search()          → GET /api/search
  get_trace()               → GET /api/v2/traces/{traceID}
  metrics_query_range()     → GET /api/metrics/query_range
  metrics_query_instant()   → GET /api/metrics/query
"""

import asyncio
import math
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx

from tempo_mcp_server.config import BackendConfig, ServerConfig
from tempo_mcp_server.exceptions import (
    TempoConnectionError,
    TempoOperationError,
    TempoQueryError,
    TempoTenantError,
)

# Tenant ID constraints per Grafana docs: max 150 bytes, restricted charset
_TENANT_PATTERN = re.compile(r"^[a-zA-Z0-9!_.\-*'()|]+$")
_TENANT_MAX_BYTES = 150

# LLM-optimized Accept header (Tempo 2.9+, experimental)
_LLM_ACCEPT = "application/vnd.grafana.llm"
_JSON_ACCEPT = "application/json"




class TempoService:
    """Async HTTP client for Grafana Tempo backends."""

    # Retryable HTTP status codes
    _RETRYABLE_STATUSES = frozenset([429, 502, 503, 504])
    # Maximum number of retry attempts for transient failures
    _MAX_RETRIES = 3
    # Base delay in seconds (doubles each attempt)
    _RETRY_BASE_DELAY = 0.5

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._backends: Dict[str, BackendConfig] = {b.id: b for b in config.backends}
        self._clients: Dict[str, httpx.AsyncClient] = {}

    # ──────────────────────────────────────────────────────────
    # Backend resolution
    # ──────────────────────────────────────────────────────────

    def _get_backend(self, backend_id: str) -> BackendConfig:
        """Resolve backend config by ID."""
        backend = self._backends.get(backend_id)
        if not backend:
            available = list(self._backends.keys())
            raise TempoOperationError(
                f"Unknown backend '{backend_id}'. Available: {available}"
            )
        return backend

    def get_default_backend_id(self) -> str:
        """Return the first configured backend ID."""
        return next(iter(self._backends))

    async def _ensure_client(self, backend_id: str) -> httpx.AsyncClient:
        """Lazy-create async HTTP client per backend with connection pooling."""
        if backend_id not in self._clients:
            backend = self._get_backend(backend_id)
            self._clients[backend_id] = httpx.AsyncClient(
                base_url=backend.base_url,
                timeout=httpx.Timeout(backend.timeout, connect=10.0),
                verify=backend.verify_ssl,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._clients[backend_id]

    # ──────────────────────────────────────────────────────────
    # Tenant / Header management
    # ──────────────────────────────────────────────────────────

    def _validate_tenant(self, tenant: str) -> None:
        """Validate tenant ID format per Grafana Tempo constraints."""
        raw = tenant.encode("utf-8")
        if len(raw) > _TENANT_MAX_BYTES:
            raise TempoTenantError(
                f"Tenant ID exceeds {_TENANT_MAX_BYTES} bytes: {len(raw)}"
            )
        # Allow pipe-separated cross-tenant queries
        for part in tenant.split("|"):
            if not _TENANT_PATTERN.match(part):
                raise TempoTenantError(
                    f"Invalid tenant ID format: '{part}'. "
                    "Allowed: alphanumeric + !-_.*'()"
                )

    def _build_headers(
        self,
        backend: BackendConfig,
        tenant: Optional[str] = None,
        accept: Optional[str] = None,
    ) -> Dict[str, str]:
        """Build request headers with tenant and auth injection."""
        headers: Dict[str, str] = {}

        if accept:
            headers["Accept"] = accept

        # Auth header
        if backend.auth_header:
            headers["Authorization"] = backend.auth_header

        # Tenant header (required for multi-tenant backends)
        effective_tenant = tenant or backend.default_tenant
        if backend.multi_tenant:
            if not effective_tenant:
                raise TempoTenantError(
                    f"Backend '{backend.id}' requires tenant ID (multi_tenant=true). "
                    "Provide 'tenant' parameter or set 'default_tenant' in config."
                )
            self._validate_tenant(effective_tenant)
            headers[backend.tenant_header] = effective_tenant
        elif effective_tenant:
            # Single-tenant but tenant provided — inject anyway (safe)
            self._validate_tenant(effective_tenant)
            headers[backend.tenant_header] = effective_tenant

        return headers

    # ──────────────────────────────────────────────────────────
    # Core HTTP request helper
    # ──────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        backend_id: str,
        path: str,
        tenant: Optional[str] = None,
        accept: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute HTTP request against a Tempo backend with retry/backoff.

        Retries up to _MAX_RETRIES times for 429/502/503/504 and transient
        connection errors, using exponential backoff. Respects Retry-After.
        """
        backend = self._get_backend(backend_id)
        client = await self._ensure_client(backend_id)
        headers = self._build_headers(backend, tenant, accept)

        # L-05: Inject a unique request ID so every Tempo backend call can be
        # correlated with this MCP tool invocation in backend access logs.
        request_id = str(uuid.uuid4())
        headers["X-Request-ID"] = request_id

        # Filter None values from params
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(self._MAX_RETRIES + 1):
            try:

                response = await client.request(
                    method=method,
                    url=path,
                    headers=headers,
                    params=params,
                    **kwargs,
                )
                response.raise_for_status()
                return response
            except httpx.ConnectError as e:
                last_exc = TempoConnectionError(
                    f"Cannot connect to Tempo backend '{backend_id}' at {backend.base_url}: {e}"
                )
                # Connection errors are retryable
                if attempt < self._MAX_RETRIES:
                    await self._backoff(attempt, None)
                    continue
                raise last_exc
            except httpx.TimeoutException as e:
                last_exc = TempoConnectionError(
                    f"Timeout connecting to '{backend_id}': {e}"
                )
                if attempt < self._MAX_RETRIES:
                    await self._backoff(attempt, None)
                    continue
                raise last_exc
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                body = e.response.text[:500]
                if status == 404:
                    raise TempoOperationError(f"Not found (404) on {path}: {body}")
                if status == 400:
                    raise TempoQueryError(f"Bad request (400) on {path}: {body}")
                if status in self._RETRYABLE_STATUSES and attempt < self._MAX_RETRIES:
                    retry_after = e.response.headers.get("Retry-After")
                    await self._backoff(attempt, retry_after)
                    continue
                if status == 429:
                    raise TempoOperationError(
                        f"Rate limited (429) by backend '{backend_id}' after "
                        f"{attempt + 1} attempt(s)"
                    )
                raise TempoOperationError(
                    f"HTTP {status} from '{backend_id}' on {path}: {body}"
                )
        raise last_exc  # unreachable, satisfies type checker

    @staticmethod
    async def _backoff(attempt: int, retry_after: Optional[str]) -> None:
        """Wait before retrying, honouring Retry-After when present."""
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = TempoService._RETRY_BASE_DELAY * (2 ** attempt)
        else:
            # Exponential backoff with a small cap
            delay = min(TempoService._RETRY_BASE_DELAY * (2 ** attempt), 8.0)
        await asyncio.sleep(delay)

    # ──────────────────────────────────────────────────────────
    # Health & Status APIs
    # ──────────────────────────────────────────────────────────

    async def check_health(self, backend_id: str) -> Dict[str, Any]:
        """GET /ready — Check backend readiness."""
        try:
            resp = await self._request("GET", backend_id, "/ready")
            return {"ready": True, "status": resp.text.strip()}
        except Exception as e:
            return {"ready": False, "error": str(e)}

    async def get_build_info(self, backend_id: str) -> Dict[str, Any]:
        """GET /api/status/buildinfo — Get version and build details."""
        resp = await self._request("GET", backend_id, "/api/status/buildinfo")
        return resp.json()

    async def get_status_services(self, backend_id: str) -> Dict[str, Any]:
        """GET /status/services — Get component service statuses.

        M-03: Tempo returns plain text (not JSON) in monolithic mode. This
        method tries JSON first, then falls back to line-by-line text parsing
        so monolithic deployments return meaningful component data instead of {}.
        """
        try:
            resp = await self._request("GET", backend_id, "/status/services")
            # Try JSON first (distributed/microservices mode)
            try:
                return resp.json()
            except Exception:
                pass
            # Fall back: parse "component: status" plain-text lines
            # e.g. "ingester: Running\ncompactor: Running"
            parsed: Dict[str, Any] = {}
            for line in resp.text.splitlines():
                line = line.strip()
                if ":" in line:
                    component, _, status = line.partition(":")
                    parsed[component.strip()] = status.strip()
            return parsed if parsed else {"raw": resp.text[:1000]}
        except Exception:
            return {}

    async def get_status_endpoints(self, backend_id: str) -> Dict[str, Any]:
        """GET /status/endpoints — Get available API endpoints."""
        try:
            resp = await self._request("GET", backend_id, "/status/endpoints")
            return resp.json()
        except Exception:
            return {}

    async def get_status_config(self, backend_id: str) -> Dict[str, Any]:
        """GET /status/config — Get runtime configuration."""
        try:
            resp = await self._request(
                "GET", backend_id, "/status/config",
                accept="application/json",
            )
            return resp.json()
        except Exception:
            return {}

    # ──────────────────────────────────────────────────────────
    # Tag / Schema Discovery APIs
    # ──────────────────────────────────────────────────────────

    async def get_attribute_names(
        self,
        backend_id: str,
        tenant: Optional[str] = None,
        scope: Optional[str] = None,
        q: Optional[str] = None,
        limit: Optional[int] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> Dict[str, Any]:
        """GET /api/v2/search/tags — Discover attribute names."""
        params: Dict[str, Any] = {}
        if scope and scope != "all":
            params["scope"] = scope
        if q:
            params["q"] = q
        if limit:
            params["limit"] = limit
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)

        resp = await self._request(
            "GET", backend_id, "/api/v2/search/tags",
            tenant=tenant, params=params,
        )
        return resp.json()

    async def get_attribute_values(
        self,
        backend_id: str,
        attribute: str,
        tenant: Optional[str] = None,
        q: Optional[str] = None,
        limit: Optional[int] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> Dict[str, Any]:
        """GET /api/v2/search/tag/{tag}/values — Get attribute values."""
        params: Dict[str, Any] = {}
        if q:
            params["q"] = q
        if limit:
            params["limit"] = limit
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)

        resp = await self._request(
            "GET", backend_id, f"/api/v2/search/tag/{attribute}/values",
            tenant=tenant, params=params,
        )
        return resp.json()

    # ──────────────────────────────────────────────────────────
    # Search APIs
    # ──────────────────────────────────────────────────────────

    async def traceql_search(
        self,
        backend_id: str,
        tenant: Optional[str] = None,
        q: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
        limit: Optional[int] = None,
        spss: Optional[int] = None,
    ) -> Dict[str, Any]:
        """GET /api/search — Execute TraceQL search."""
        params: Dict[str, Any] = {}
        if q:
            params["q"] = q
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)
        if limit:
            params["limit"] = limit
        if spss:
            params["spss"] = spss

        resp = await self._request(
            "GET", backend_id, "/api/search",
            tenant=tenant, params=params,
        )
        return resp.json()

    async def get_trace(
        self,
        backend_id: str,
        trace_id: str,
        tenant: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
        llm_format: bool = True,
        max_spans: Optional[int] = None,
    ) -> Dict[str, Any]:
        """GET /api/v2/traces/{traceID} — Retrieve a single trace.

        Attempts LLM format first (application/vnd.grafana.llm),
        falls back to standard JSON if unavailable.

        L-02: When max_spans is set, slices the spans list and reports
        truncation metadata so the caller knows data was cut.

        C-01 (envelope unwrap): Tempo /api/v2/traces returns a two-level
        structure: {"trace": {"resourceSpans": [...]}, "metrics": {...}}.
        We unwrap the inner "trace" key so that downstream consumers
        (_apply_span_limit, trace_summarizer._extract_spans) always receive
        a plain OTLP payload with "resourceSpans" / "batches" at the root.
        """
        backend = self._get_backend(backend_id)
        params: Dict[str, Any] = {}
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)

        # Try LLM format if supported and requested
        accept = _LLM_ACCEPT if (llm_format and backend.llm_format_supported) else _JSON_ACCEPT
        used_llm = accept == _LLM_ACCEPT

        try:
            resp = await self._request(
                "GET", backend_id, f"/api/v2/traces/{trace_id}",
                tenant=tenant, accept=accept, params=params,
            )
            data = resp.json()
            # Unwrap Tempo's outer envelope: {"trace": <otlp>, "metrics": {...}}
            data = data.get("trace", data) if isinstance(data.get("trace"), dict) else data
            data, trunc_meta = self._apply_span_limit(data, max_spans)
            return {"trace": data, "llm_format_used": used_llm, **trunc_meta}
        except TempoOperationError:
            if used_llm:
                # Fallback to standard JSON
                resp = await self._request(
                    "GET", backend_id, f"/api/v2/traces/{trace_id}",
                    tenant=tenant, accept=_JSON_ACCEPT, params=params,
                )
                data = resp.json()
                # Unwrap Tempo's outer envelope in the fallback path too
                data = data.get("trace", data) if isinstance(data.get("trace"), dict) else data
                data, trunc_meta = self._apply_span_limit(data, max_spans)
                return {"trace": data, "llm_format_used": False, **trunc_meta}
            raise

    @staticmethod
    def _apply_span_limit(
        trace_data: Dict[str, Any],
        max_spans: Optional[int],
    ) -> tuple:
        """Slice spans to max_spans and return truncation metadata.

        L-02: Large traces (10k+ spans) can easily exceed the 100KB middleware
        limit. Slicing server-side and reporting the cut prevents silent
        truncation by the ResponseLimitingMiddleware.

        Returns:
            (possibly_sliced_data, meta_dict)
            meta_dict keys: truncated, total_spans, returned_spans
        """
        if max_spans is None:
            return trace_data, {}

        # OTLP JSON: resourceSpans[].scopeSpans[].spans[]
        total = 0
        resource_spans = trace_data.get("resourceSpans", [])
        for rs in resource_spans:
            for ss in rs.get("scopeSpans", []):
                total += len(ss.get("spans", []))

        if total <= max_spans:
            return trace_data, {"truncated": False, "total_spans": total, "returned_spans": total}

        # Slice: keep the first max_spans spans across resourceSpans in order
        remaining = max_spans
        sliced_rs = []
        for rs in resource_spans:
            if remaining <= 0:
                break
            sliced_ss = []
            for ss in rs.get("scopeSpans", []):
                if remaining <= 0:
                    break
                spans = ss.get("spans", [])
                kept = spans[:remaining]
                remaining -= len(kept)
                sliced_ss.append({**ss, "spans": kept})
            sliced_rs.append({**rs, "scopeSpans": sliced_ss})

        sliced_data = {**trace_data, "resourceSpans": sliced_rs}
        return sliced_data, {
            "truncated": True,
            "total_spans": total,
            "returned_spans": max_spans,
            "truncation_note": (
                f"Trace has {total} spans. Only the first {max_spans} are returned. "
                "Use a larger max_spans value or summarize with tempo_summarize_trace."
            ),
        }

    # ──────────────────────────────────────────────────────────
    # TraceQL Metrics APIs
    # ──────────────────────────────────────────────────────────

    async def metrics_query_range(
        self,
        backend_id: str,
        q: str,
        tenant: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
        step: Optional[str] = None,
        exemplars: bool = False,
    ) -> Dict[str, Any]:
        """GET /api/metrics/query_range — TraceQL range metrics query."""
        params: Dict[str, Any] = {"q": q}
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)
        if step:
            params["step"] = step
        if exemplars:
            params["exemplars"] = "true"

        resp = await self._request(
            "GET", backend_id, "/api/metrics/query_range",
            tenant=tenant, params=params,
        )
        return resp.json()

    async def metrics_query_instant(
        self,
        backend_id: str,
        q: str,
        tenant: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> Dict[str, Any]:
        """GET /api/metrics/query — TraceQL instant metrics query."""
        params: Dict[str, Any] = {"q": q}
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)

        resp = await self._request(
            "GET", backend_id, "/api/metrics/query",
            tenant=tenant, params=params,
        )
        return resp.json()

    # ──────────────────────────────────────────────────────────
    # Ring / Diagnostics APIs
    # ──────────────────────────────────────────────────────────

    # NOTE: detect_deployment_mode() was removed (B-03 revision).
    # Auto-detecting monolithic vs. microservices by probing /status/services
    # or /distributor/ring is unreliable: in distributed deployments, the MCP
    # server typically hits the query-frontend (or a gateway), whose
    # /status/services only reports that pod's internal services — not cluster-
    # wide components.  Set TEMPO_DEPLOYMENT_MODE="microservices" explicitly.

    async def check_rings(
        self,
        backend_id: str,
        deployment_mode_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check distributor/ingester/compactor ring status.

        L-04: Parses ring HTML/text to extract structured member counts and
        state distributions instead of returning raw HTML to the LLM.

        H-02: In monolithic deployment mode, /distributor/ring and
        /compactor/ring are not exposed; only /ingester/ring (and sometimes
        /ring) exists.  Hitting the missing endpoints returns 404, which was
        previously treated as a degraded-ring finding.  We now skip
        microservice-only rings when deployment_mode == "monolithic" and
        attempt the unified /ring endpoint instead.

        Args:
            backend_id: Backend to check.
            deployment_mode_override: If provided, overrides the backend's
                configured deployment_mode. Used by diagnostics auto-detection
                to avoid mutating BackendConfig.
        """
        backend = self._get_backend(backend_id)
        effective_mode = deployment_mode_override or backend.deployment_mode

        if effective_mode == "monolithic":
            # Monolithic exposes /ingester/ring and sometimes /ring
            ring_paths = ["/ingester/ring"]
        else:
            ring_paths = ["/distributor/ring", "/ingester/ring", "/compactor/ring"]

        results: Dict[str, Any] = {}
        for path in ring_paths:
            component = path.strip("/").replace("/", "_")
            try:
                resp = await self._request("GET", backend_id, path)
                results[component] = self._parse_ring_response(resp.text)
            except Exception as e:
                results[component] = {"status": "error", "error": str(e)}

        if effective_mode == "monolithic":
            results["_deployment_note"] = (
                "Monolithic mode: distributor/compactor rings are not exposed. "
                "Only ingester ring is checked."
            )

        return results

    @staticmethod
    def _parse_ring_response(text: str) -> Dict[str, Any]:
        """Parse Tempo ring HTML/text into structured member + state data.

        L-04: Ring endpoints return HTML tables or plain text. This extracts
        member counts and state distributions so AI agents can reason about
        ring health without parsing HTML.

        Handles two common formats:
          - HTML tables: <td>...</td> rows with member, state, addr columns
          - Plain text: "member=<addr> state=<STATE>" key=value lines
        """
        states: Dict[str, int] = {}
        member_count = 0

        # Try extracting state values from HTML <td> content
        # Ring HTML typically has rows: <tr><td>token</td><td>addr</td><td>STATE</td>...</tr>
        td_values = re.findall(r"<td[^>]*>([^<]+)</td>", text, re.IGNORECASE)
        known_states = {"ACTIVE", "LEAVING", "PENDING", "JOINING", "LEFT"}
        for val in td_values:
            val = val.strip().upper()
            if val in known_states:
                states[val] = states.get(val, 0) + 1
                member_count += 1

        # Fallback: plain text "STATE=ACTIVE" or "state: ACTIVE" patterns
        if not states:
            for match in re.finditer(r"\bstate[=:\s]+([A-Z]+)", text, re.IGNORECASE):
                val = match.group(1).upper()
                if val in known_states:
                    states[val] = states.get(val, 0) + 1
                    member_count += 1

        return {
            "status": "ok",
            "total_members": member_count,
            "active": states.get("ACTIVE", 0),
            "leaving": states.get("LEAVING", 0),
            "pending": states.get("PENDING", 0),
            "states": states if states else None,
            "parse_note": (
                None if states else
                "Could not extract member states from ring response. Raw text unavailable."
            ),
        }

    # ──────────────────────────────────────────────────────────
    # Backend listing / capabilities
    # ──────────────────────────────────────────────────────────

    async def list_backends(self) -> List[Dict[str, Any]]:
        """Return all configured backends with health status."""
        results = []
        for bid, backend in self._backends.items():
            health = await self.check_health(bid)
            results.append({
                "id": bid,
                "type": backend.type,
                "display_name": backend.display_name,
                "base_url": backend.base_url,
                "deployment_mode": backend.deployment_mode,
                "multi_tenant": backend.multi_tenant,
                "health": "ready" if health.get("ready") else "not_ready",
            })
        return results

    async def get_backend_capabilities(self, backend_id: str) -> Dict[str, Any]:
        """Combine health + buildinfo + status for a backend profile."""
        backend = self._get_backend(backend_id)
        health = await self.check_health(backend_id)

        result: Dict[str, Any] = {
            "id": backend_id,
            "type": backend.type,
            "display_name": backend.display_name,
            "base_url": backend.base_url,
            "deployment_mode": backend.deployment_mode,
            "multi_tenant": backend.multi_tenant,
            "health": "ready" if health.get("ready") else "not_ready",
            "capabilities": [],
        }

        # Build info
        try:
            build_info = await self.get_build_info(backend_id)
            result["build_info"] = build_info
            data = build_info.get("data", build_info)
            result["version"] = data.get("version")
        except Exception:
            pass

        # Services
        try:
            services = await self.get_status_services(backend_id)
            result["services"] = services
        except Exception:
            pass

        # Tenant requirements
        if backend.multi_tenant:
            result["tenant_requirements"] = "required"
        else:
            result["tenant_requirements"] = "not_applicable"

        # Infer capabilities
        caps = ["search", "trace_by_id"]
        try:
            endpoints = await self.get_status_endpoints(backend_id)
            if endpoints:
                caps.append("schema_discovery")
        except Exception:
            pass
        caps.append("traceql_metrics")  # Assume available; diagnostics will verify
        result["capabilities"] = caps

        return result

    def add_backend(self, backend: BackendConfig) -> None:
        """Dynamically add a backend (used by K8s discovery)."""
        self._backends[backend.id] = backend

    # ──────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
