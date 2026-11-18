"""Tempo HTTP API service.

Core async HTTP client wrapping all Tempo backend APIs:
  check_health()                  -> GET /ready
  get_build_info()                -> GET /api/status/buildinfo
  get_status_services()           -> GET /status/services
  get_status_endpoints()          -> GET /status/endpoints
  get_status_config()             -> GET /status/config
  get_safe_status_config()        -> GET /status/config (allow-listed non-secret facts)
  get_prometheus_metrics_facts()  -> GET /metrics (discarded spans & partition lag facts)
  get_tenant_overrides()          -> GET /api/overrides
  patch_tenant_overrides()        -> PATCH /api/overrides (with ETag / If-Match)
  get_attribute_names()           -> GET /api/v2/search/tags
  get_attribute_values()          -> GET /api/v2/search/tag/{tag}/values
  traceql_search()                -> GET /api/search
  get_trace()                     -> GET /api/v2/traces/{traceID}
  metrics_query_range()           -> GET /api/metrics/query_range
  metrics_query_instant()         -> GET /api/metrics/query
  check_rings()                   -> GET /ingester/ring (2.x) or /live-store/ring & /partition-ring (3.x)
"""

import asyncio
import copy
import re
import uuid
from typing import Any, Dict, List, Optional

import httpx
import yaml

from tempo_mcp_server.config import BackendConfig, ServerConfig
from tempo_mcp_server.exceptions import (
    TempoConnectionError,
    TempoOperationError,
    TempoQueryError,
    TempoTenantError,
)
from tempo_mcp_server.utils.prom_text import extract_tempo_metrics_facts
from tempo_mcp_server.utils.redaction import extract_safe_status_config

# Tenant ID constraints per Grafana docs: max 150 bytes, restricted charset
_TENANT_PATTERN = re.compile(r"^[a-zA-Z0-9!_.\-*'()|]+$")
_TENANT_MAX_BYTES = 150

# LLM-optimized Accept header (Tempo 2.9+, experimental)
_LLM_ACCEPT = "application/vnd.grafana.llm"
_JSON_ACCEPT = "application/json"


class TempoService:
    """Async HTTP client for Grafana Tempo 2.x and 3.x backends."""

    _RETRYABLE_STATUSES = frozenset([429, 502, 503, 504])
    _MAX_RETRIES = 3
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
        extra_headers: Optional[Dict[str, str]] = None,
        require_tenant: bool = True,
    ) -> Dict[str, str]:
        """Build request headers with tenant and auth injection."""
        headers: Dict[str, str] = {}

        if accept:
            headers["Accept"] = accept

        if backend.auth_header:
            headers["Authorization"] = backend.auth_header

        effective_tenant = tenant or backend.default_tenant
        if backend.multi_tenant:
            if not effective_tenant:
                if require_tenant:
                    raise TempoTenantError(
                        f"Backend '{backend.id}' requires tenant ID (multi_tenant=true). "
                        "Provide 'tenant' parameter or set 'default_tenant' in config."
                    )
            else:
                self._validate_tenant(effective_tenant)
                headers[backend.tenant_header] = effective_tenant
        elif effective_tenant:
            self._validate_tenant(effective_tenant)
            headers[backend.tenant_header] = effective_tenant

        if extra_headers:
            headers.update(extra_headers)

        return headers

    # ──────────────────────────────────────────────────────────
    # Core HTTP request helper
    # ──────────────────────────────────────────────────────────

    _CLUSTER_ADMIN_PATHS = frozenset({
        "/ready",
        "/api/echo",
        "/api/status/buildinfo",
        "/status/services",
        "/status/endpoints",
        "/status/config",
        "/metrics",
    })

    async def _request(
        self,
        method: str,
        backend_id: str,
        path: str,
        tenant: Optional[str] = None,
        accept: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute HTTP request against a Tempo backend with retry/backoff."""
        backend = self._get_backend(backend_id)
        client = await self._ensure_client(backend_id)
        clean_path = path.split("?", 1)[0]
        is_cluster_admin = clean_path in self._CLUSTER_ADMIN_PATHS or "ring" in clean_path
        headers = self._build_headers(
            backend,
            tenant,
            accept,
            extra_headers=extra_headers,
            require_tenant=not is_cluster_admin,
        )

        request_id = str(uuid.uuid4())
        headers["X-Request-ID"] = request_id

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
                if status == 412:
                    raise TempoOperationError(
                        f"Precondition failed (412) on {path}: ETag mismatch ({body})"
                    )
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
        raise last_exc

    @staticmethod
    async def _backoff(attempt: int, retry_after: Optional[str]) -> None:
        """Wait before retrying, honouring Retry-After when present."""
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = TempoService._RETRY_BASE_DELAY * (2 ** attempt)
        else:
            delay = min(TempoService._RETRY_BASE_DELAY * (2 ** attempt), 8.0)
        await asyncio.sleep(delay)

    # ──────────────────────────────────────────────────────────
    # Health, BuildInfo, Config & Metrics APIs
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
        """GET /status/services — Get component service statuses (JSON, ASCII table, or key:value)."""
        try:
            resp = await self._request("GET", backend_id, "/status/services")
            try:
                data = resp.json()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            parsed: Dict[str, Any] = {}
            for raw_line in resp.text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("+") or line.upper().startswith("GET "):
                    continue
                if line.startswith("|") and line.endswith("|"):
                    cols = [c.strip() for c in line.strip("|").split("|")]
                    if len(cols) >= 2 and cols[0] and cols[0].upper() not in ("SERVICE NAME", "MODULE", "COMPONENT"):
                        parsed[cols[0]] = cols[1]
                elif ":" in line:
                    component, _, status = line.partition(":")
                    comp = component.strip()
                    if comp and comp.upper() != "SERVICE NAME":
                        parsed[comp] = status.strip()
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
        """GET /status/config — Get raw runtime configuration (JSON or YAML)."""
        try:
            resp = await self._request(
                "GET", backend_id, "/status/config",
                accept="application/json",
            )
            try:
                parsed = resp.json()
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            loaded = yaml.safe_load(resp.text)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            try:
                resp = await self._request("GET", backend_id, "/status/config")
                loaded = yaml.safe_load(resp.text)
                return loaded if isinstance(loaded, dict) else {}
            except Exception:
                return {}

    async def get_safe_status_config(self, backend_id: str) -> Dict[str, Any]:
        """GET /status/config filtered through strict allow-list extraction (0->1 secret omission)."""
        raw = await self.get_status_config(backend_id)
        return extract_safe_status_config(raw)

    async def get_prometheus_metrics_facts(self, backend_id: str) -> Optional[Dict[str, Any]]:
        """GET /metrics — Scrape Tempo Prometheus metrics for discarded spans and partition lag."""
        try:
            resp = await self._request("GET", backend_id, "/metrics")
            return extract_tempo_metrics_facts(resp.text)
        except Exception:
            return None

    @staticmethod
    def detect_tempo_generation(
        build_info: Optional[Dict[str, Any]] = None,
        services: Optional[Dict[str, Any]] = None,
        config_facts: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[int], str]:
        """Detect Tempo major version and architecture generation ('2.x', '3.x', or 'unknown')."""
        if build_info and isinstance(build_info, dict):
            data = build_info.get("data", build_info)
            version_str = str(data.get("version", ""))
            m = re.search(r"\bv?(\d+)\.\d+", version_str)
            if m:
                major = int(m.group(1))
                return major, f"{major}.x"

        # Check Tempo 3.0 service / config indicators (Project Rhythm: live-store, block-builder)
        v3_components = {"live-store", "live_store", "block-builder", "block_builder", "backend-scheduler", "backend-worker"}
        if services and isinstance(services, dict):
            svc_keys = {k.lower() for k in services.keys()}
            if svc_keys & v3_components:
                return 3, "3.x"
            if "ingester" in svc_keys:
                return 2, "2.x"

        if config_facts and config_facts.get("v3_components_configured"):
            return 3, "3.x"

        return None, "unknown"

    # ──────────────────────────────────────────────────────────
    # User-Configurable Overrides API (/api/overrides)
    # ──────────────────────────────────────────────────────────

    async def get_tenant_overrides(
        self,
        backend_id: str,
        tenant: Optional[str] = None,
        scope: str = "merged",
    ) -> Dict[str, Any]:
        """GET /api/overrides — Retrieve tenant-specific overrides and ETag."""
        backend = self._get_backend(backend_id)
        effective_tenant = tenant or backend.default_tenant or "single-tenant"
        try:
            resp = await self._request(
                "GET",
                backend_id,
                "/api/overrides",
                tenant=effective_tenant,
                accept=_JSON_ACCEPT,
                params={"scope": scope},
            )
        except TempoOperationError as exc:
            msg = str(exc)
            # In Tempo 2.x user_configurable_overrides, a tenant without custom UCO yet returns 404 with empty body
            if msg.startswith("Not found (404) on /api/overrides:") and not msg.split(":", 1)[1].strip():
                return {
                    "backend_id": backend_id,
                    "tenant": effective_tenant,
                    "scope": scope,
                    "etag": '""',
                    "overrides": {},
                }
            raise
        etag = resp.headers.get("ETag") or resp.headers.get("Etag")
        return {
            "backend_id": backend_id,
            "tenant": effective_tenant,
            "scope": scope,
            "etag": etag,
            "overrides": resp.json() if resp.content else {},
        }

    @staticmethod
    def _rfc7386_merge_dict(target: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        result = copy.deepcopy(target) if isinstance(target, dict) else {}
        for k, v in patch.items():
            if v is None:
                result.pop(k, None)
            elif isinstance(v, dict):
                result[k] = TempoService._rfc7386_merge_dict(result.get(k, {}), v)
            else:
                result[k] = copy.deepcopy(v)
        return result

    async def patch_tenant_overrides(
        self,
        backend_id: str,
        tenant: str,
        merge_patch: Dict[str, Any],
        expected_etag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """PATCH /api/overrides (or POST /api/overrides fallback on Tempo 2.x) with If-Match ETag."""
        extra_headers: Dict[str, str] = {"Content-Type": "application/json"}
        if expected_etag:
            extra_headers["If-Match"] = expected_etag

        uco_note: Optional[str] = None
        try:
            resp = await self._request(
                "PATCH",
                backend_id,
                "/api/overrides",
                tenant=tenant,
                accept=_JSON_ACCEPT,
                extra_headers=extra_headers,
                json=merge_patch,
            )
        except TempoOperationError as exc:
            if "HTTP 405" not in str(exc) and "405" not in str(exc):
                raise
            current_overrides: Dict[str, Any] = {}
            try:
                cur = await self.get_tenant_overrides(
                    backend_id=backend_id,
                    tenant=tenant,
                    scope="api",
                )
                current_overrides = cur.get("overrides") or {}
                if not expected_etag and cur.get("etag"):
                    extra_headers["If-Match"] = cur["etag"]
            except TempoOperationError as get_exc:
                if "Not found (404)" not in str(get_exc):
                    raise
            if "If-Match" not in extra_headers:
                extra_headers["If-Match"] = '""'
            merged_doc = self._rfc7386_merge_dict(current_overrides, merge_patch)
            try:
                resp = await self._request(
                    "POST",
                    backend_id,
                    "/api/overrides",
                    tenant=tenant,
                    accept=_JSON_ACCEPT,
                    extra_headers=extra_headers,
                    json=merged_doc,
                )
                merge_patch = merged_doc
            except TempoQueryError as q_exc:
                if "client.Limits.ReadObject: found unknown field" not in str(q_exc):
                    raise
                uco_allowed = {"metrics_generator", "cost_attribution", "forwarders"}
                uco_subset = {k: v for k, v in merged_doc.items() if k in uco_allowed}
                dropped = sorted(k for k in merged_doc.keys() if k not in uco_allowed)
                resp = await self._request(
                    "POST",
                    backend_id,
                    "/api/overrides",
                    tenant=tenant,
                    accept=_JSON_ACCEPT,
                    extra_headers=extra_headers,
                    json=uco_subset,
                )
                merge_patch = merged_doc
                uco_note = (
                    f"OSS Tempo 2.x user_configurable_overrides persisted {sorted(uco_subset.keys())}; "
                    f"operator-level limits {dropped} require per_tenant_override_config (overrides.yaml / TempoStack)."
                )

        new_etag = resp.headers.get("ETag") or resp.headers.get("Etag")
        body = resp.json() if resp.content else merge_patch
        if not new_etag:
            try:
                refreshed = await self.get_tenant_overrides(
                    backend_id=backend_id,
                    tenant=tenant,
                    scope="api",
                )
                new_etag = refreshed.get("etag")
                if refreshed.get("overrides") and not uco_note:
                    body = refreshed["overrides"]
            except Exception:
                pass
        out: Dict[str, Any] = {
            "backend_id": backend_id,
            "tenant": tenant,
            "etag": new_etag,
            "overrides": body,
        }
        if uco_note:
            out["uco_schema_note"] = uco_note
        return out

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

    async def detect_live_attributes(
        self,
        backend_id: str,
        tenant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Inspect live tags on a backend and report present attributes and detected OTel SemConv."""
        tags_resp = await self.get_attribute_names(backend_id=backend_id, tenant=tenant)
        by_scope: Dict[str, List[str]] = {}
        all_tags: set[str] = set()

        for scope_entry in tags_resp.get("scopes", []):
            sname = scope_entry.get("name", "unknown")
            tags = [
                t.get("name", t) if isinstance(t, dict) else str(t)
                for t in scope_entry.get("tags", [])
            ]
            by_scope[sname] = sorted(tags)
            all_tags.update(tags)

        # Detect OTel SemConv v1.21+ vs legacy attributes based on live presence
        detected_semconv = {
            "http_status_code": (
                "http.response.status_code"
                if "http.response.status_code" in all_tags
                else "http.status_code"
            ),
            "http_method": (
                "http.request.method"
                if "http.request.method" in all_tags
                else "http.method"
            ),
            "url_path": (
                "url.path"
                if "url.path" in all_tags
                else "http.target"
            ),
            "environment": (
                "deployment.environment.name"
                if "deployment.environment.name" in all_tags
                else "deployment.environment"
            ),
            "peer_service": (
                "server.address"
                if ("server.address" in all_tags and "peer.service" not in all_tags)
                else "peer.service"
            ),
        }

        k8s_present = sorted(t for t in all_tags if t.startswith("k8s.") or t in ("service.name", "namespace", "pod", "cluster"))

        return {
            "backend_id": backend_id,
            "scopes": by_scope,
            "total_attributes": len(all_tags),
            "k8s_attributes_present": k8s_present,
            "detected_semconv": detected_semconv,
        }

    # ──────────────────────────────────────────────────────────
    # Search & Trace Retrieval APIs
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
        """GET /api/v2/traces/{traceID} — Retrieve a single trace."""
        backend = self._get_backend(backend_id)
        params: Dict[str, Any] = {}
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)

        accept = _LLM_ACCEPT if (llm_format and backend.llm_format_supported) else _JSON_ACCEPT
        used_llm = accept == _LLM_ACCEPT

        try:
            resp = await self._request(
                "GET", backend_id, f"/api/v2/traces/{trace_id}",
                tenant=tenant, accept=accept, params=params,
            )
            data = resp.json()
            data = data.get("trace", data) if isinstance(data.get("trace"), dict) else data
            data, trunc_meta = self._apply_span_limit(data, max_spans)
            return {"trace": data, "llm_format_used": used_llm, **trunc_meta}
        except TempoOperationError:
            if used_llm:
                resp = await self._request(
                    "GET", backend_id, f"/api/v2/traces/{trace_id}",
                    tenant=tenant, accept=_JSON_ACCEPT, params=params,
                )
                data = resp.json()
                data = data.get("trace", data) if isinstance(data.get("trace"), dict) else data
                data, trunc_meta = self._apply_span_limit(data, max_spans)
                return {"trace": data, "llm_format_used": False, **trunc_meta}
            raise

    @staticmethod
    def _apply_span_limit(
        trace_data: Dict[str, Any],
        max_spans: Optional[int],
    ) -> tuple:
        """Slice spans to max_spans and return truncation metadata."""
        if max_spans is None:
            return trace_data, {}

        total = 0
        resource_spans = trace_data.get("resourceSpans", [])
        for rs in resource_spans:
            for ss in rs.get("scopeSpans", []):
                total += len(ss.get("spans", []))

        if total <= max_spans:
            return trace_data, {"truncated": False, "total_spans": total, "returned_spans": total}

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
            "truncation_note": f"Returned {max_spans} of {total} spans.",
        }

    # ──────────────────────────────────────────────────────────
    # TraceQL Metrics APIs
    # ──────────────────────────────────────────────────────────

    _TOPK_RE = re.compile(r"^(.*?)\|\s*(topk|bottomk)\s*\(\s*(\d+)\s*\)(\s*(?:with\s*\([^)]*\))?)\s*$", re.IGNORECASE)

    @staticmethod
    def _extract_otlp_any_value(val_obj: Any) -> str:
        if not isinstance(val_obj, dict):
            return str(val_obj)
        for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if k in val_obj:
                return str(val_obj[k])
        return str(val_obj)

    @classmethod
    def _normalize_tempo_metrics_response(
        cls,
        raw: Dict[str, Any],
        *,
        is_instant: bool = False,
        agg_mode: str = "avg",
        topk_limit: Optional[tuple[str, int]] = None,
    ) -> Dict[str, Any]:
        """Normalize Tempo native ProtoJSON {'series': [...]} into {'data': {'resultType': ..., 'result': [...], 'exemplars': [...]}, ...}."""
        if not isinstance(raw, dict):
            return raw
        if "data" in raw and isinstance(raw["data"], dict) and "result" in raw["data"]:
            if topk_limit:
                op, k_n = topk_limit
                res_list = list(raw["data"].get("result", []))
                def _score_prom(it: Dict[str, Any]) -> float:
                    if "value" in it and isinstance(it["value"], list) and len(it["value"]) >= 2:
                        try:
                            return float(it["value"][1])
                        except Exception:
                            return 0.0
                    vals = [float(v[1]) for v in it.get("values", []) if len(v) >= 2]
                    return (sum(vals) / len(vals)) if vals else 0.0
                res_list.sort(key=_score_prom, reverse=(op == "topk"))
                raw = {**raw, "data": {**raw["data"], "result": res_list[:k_n]}}
            return raw
        if "series" not in raw or not isinstance(raw.get("series"), list):
            return raw

        result_items: List[Dict[str, Any]] = []
        exemplar_items: List[Dict[str, Any]] = []
        seen_exemplars: set[str] = set()

        for s in raw.get("series", []):
            if not isinstance(s, dict):
                continue
            labels_dict: Dict[str, str] = {}
            for lbl in s.get("labels", []) or []:
                if isinstance(lbl, dict) and "key" in lbl:
                    labels_dict[str(lbl["key"])] = cls._extract_otlp_any_value(lbl.get("value", ""))

            for ex in s.get("exemplars", []) or []:
                if not isinstance(ex, dict):
                    continue
                ex_labels: Dict[str, str] = dict(labels_dict)
                tid = ""
                for el in ex.get("labels", []) or []:
                    if isinstance(el, dict) and "key" in el:
                        ek = str(el["key"])
                        ev = cls._extract_otlp_any_value(el.get("value", ""))
                        ex_labels[ek] = ev
                        if ek in ("trace:id", "traceID", "trace_id", "traceId"):
                            tid = ev
                if tid and tid not in seen_exemplars:
                    seen_exemplars.add(tid)
                    ts_ms = ex.get("timestampMs")
                    exemplar_items.append({
                        "traceID": tid,
                        "timestamp": (float(ts_ms) / 1000.0) if ts_ms is not None else None,
                        "value": ex.get("value"),
                        "labels": ex_labels,
                    })

            samples = s.get("samples")
            if is_instant:
                scalar_val: Optional[float] = None
                if "value" in s and s["value"] is not None:
                    try:
                        scalar_val = float(s["value"])
                    except (ValueError, TypeError):
                        scalar_val = 0.0
                elif isinstance(samples, list):
                    non_empty = [float(smp["value"]) for smp in samples if isinstance(smp, dict) and "value" in smp]
                    if non_empty:
                        scalar_val = sum(non_empty) if agg_mode == "sum" else (sum(non_empty) / len(non_empty))
                    else:
                        scalar_val = 0.0
                else:
                    scalar_val = 0.0
                ts_sec = 0.0
                if isinstance(samples, list) and samples:
                    last_ts = samples[-1].get("timestampMs")
                    if last_ts is not None:
                        ts_sec = float(last_ts) / 1000.0
                result_items.append({
                    "metric": labels_dict,
                    "value": [ts_sec, str(round(scalar_val, 6))],
                })
            else:
                values_pairs: List[List[Any]] = []
                for smp in samples or []:
                    if isinstance(smp, dict) and "value" in smp and smp.get("timestampMs") is not None:
                        values_pairs.append([float(smp["timestampMs"]) / 1000.0, str(smp["value"])])
                if values_pairs:
                    result_items.append({
                        "metric": labels_dict,
                        "values": values_pairs,
                    })

        if topk_limit:
            op, k_n = topk_limit
            def _score_item(it: Dict[str, Any]) -> float:
                if "value" in it:
                    try:
                        return float(it["value"][1])
                    except Exception:
                        return 0.0
                vals = [float(v[1]) for v in it.get("values", []) if len(v) >= 2]
                return (sum(vals) / len(vals)) if vals else 0.0
            # Filter zero-only items when ranking topk so active error services surface cleanly
            if op == "topk":
                non_zero_items = [it for it in result_items if _score_item(it) > 0]
                if non_zero_items:
                    result_items = non_zero_items
            result_items.sort(key=_score_item, reverse=(op == "topk"))
            result_items = result_items[:k_n]

        return {
            **raw,
            "data": {
                "resultType": "vector" if is_instant else "matrix",
                "result": result_items,
                "exemplars": exemplar_items,
            },
        }

    @classmethod
    def _split_topk_clause(cls, q: str) -> tuple[str, Optional[tuple[str, int]]]:
        m = cls._TOPK_RE.match(q.strip())
        if not m:
            return q, None
        base_q = f"{m.group(1).rstrip()}{m.group(4)}".strip()
        return base_q, (m.group(2).lower(), int(m.group(3)))

    async def metrics_query_range(
        self,
        backend_id: str,
        q: str,
        tenant: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
        step: Optional[str] = None,
        exemplars: bool = False,
        sample: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /api/metrics/query_range — TraceQL range metrics query."""
        base_q, topk_spec = self._split_topk_clause(q)
        params: Dict[str, Any] = {"q": q}
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)
        if step:
            params["step"] = step
        if exemplars:
            params["exemplars"] = "true"
        effective_sample = sample or self._config.query_policy.default_metrics_sampling
        if effective_sample:
            params["sample"] = effective_sample

        try:
            resp = await self._request(
                "GET", backend_id, "/api/metrics/query_range",
                tenant=tenant, params=params,
            )
            return self._normalize_tempo_metrics_response(resp.json(), is_instant=False, topk_limit=topk_spec)
        except (TempoQueryError, TempoOperationError) as exc:
            if topk_spec and ("parse error" in str(exc).lower() or "syntax error" in str(exc).lower()):
                params["q"] = base_q
                resp = await self._request(
                    "GET", backend_id, "/api/metrics/query_range",
                    tenant=tenant, params=params,
                )
                return self._normalize_tempo_metrics_response(resp.json(), is_instant=False, topk_limit=topk_spec)
            raise

    async def metrics_query_instant(
        self,
        backend_id: str,
        q: str,
        tenant: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
        sample: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /api/metrics/query — TraceQL instant metrics query (with Tempo 2.x window & topk support)."""
        base_q, topk_spec = self._split_topk_clause(q)
        agg_mode = "sum" if any(fn in base_q for fn in ("compare(", "count_over_time(", "sum_over_time(")) else "avg"
        params: Dict[str, Any] = {"q": q}
        if start:
            params["start"] = int(start)
        if end:
            params["end"] = int(end)
        effective_sample = sample or self._config.query_policy.default_metrics_sampling
        if effective_sample:
            params["sample"] = effective_sample

        raw_json: Dict[str, Any]
        used_query = q
        try:
            resp = await self._request(
                "GET", backend_id, "/api/metrics/query",
                tenant=tenant, params=params,
            )
            raw_json = resp.json()
        except (TempoQueryError, TempoOperationError) as exc:
            if topk_spec and ("parse error" in str(exc).lower() or "syntax error" in str(exc).lower()):
                used_query = base_q
                params["q"] = base_q
                resp = await self._request(
                    "GET", backend_id, "/api/metrics/query",
                    tenant=tenant, params=params,
                )
                raw_json = resp.json()
            else:
                raise

        # In Tempo 2.x, /api/metrics/query evaluates only the final instant step at `end` and omits `value`
        # when spans occurred earlier in `[start, end]`. Aggregate over `[start, end]` via query_range when needed.
        if (
            isinstance(raw_json, dict)
            and "series" in raw_json
            and "data" not in raw_json
            and start is not None
            and end is not None
            and (end - start) > 30
            and not any("value" in s for s in raw_json.get("series", []) if isinstance(s, dict))
        ):
            span_sec = max(60, int((end - start) / 12))
            range_params = {**params, "q": used_query, "step": f"{span_sec}s"}
            try:
                r_resp = await self._request(
                    "GET", backend_id, "/api/metrics/query_range",
                    tenant=tenant, params=range_params,
                )
                raw_json = r_resp.json()
            except Exception:
                pass

        return self._normalize_tempo_metrics_response(
            raw_json,
            is_instant=True,
            agg_mode=agg_mode,
            topk_limit=topk_spec,
        )

    # ──────────────────────────────────────────────────────────
    # Ring / Diagnostics APIs (Version-aware 2.x vs 3.x)
    # ──────────────────────────────────────────────────────────

    async def check_rings(
        self,
        backend_id: str,
        deployment_mode_override: Optional[str] = None,
        architecture_generation: str = "2.x",
    ) -> Dict[str, Any]:
        """Check ring status across Tempo 2.x (ingester/distributor/compactor) or 3.x (live-store/partition-ring)."""
        backend = self._get_backend(backend_id)
        effective_mode = deployment_mode_override or backend.deployment_mode

        if architecture_generation == "3.x":
            if effective_mode == "monolithic":
                return {
                    "_deployment_note": "Tempo 3.x monolithic mode runs in-process without distributed rings."
                }
            ring_paths = ["/live-store/ring", "/partition-ring"]
        else:
            if effective_mode == "monolithic":
                ring_paths = ["/ingester/ring"]
            else:
                ring_paths = ["/distributor/ring", "/ingester/ring", "/compactor/ring"]

        results: Dict[str, Any] = {}
        for path in ring_paths:
            component = path.strip("/").replace("/", "_").replace("-", "_")
            try:
                resp = await self._request("GET", backend_id, path)
                results[component] = self._parse_ring_response(resp.text)
            except Exception as e:
                results[component] = {"status": "error", "error": str(e)}

        if effective_mode == "monolithic" and architecture_generation != "3.x":
            results["_deployment_note"] = (
                "Monolithic mode: distributor/compactor rings are not exposed. "
                "Only ingester ring is checked."
            )

        return results

    @staticmethod
    def _parse_ring_response(text: str) -> Dict[str, Any]:
        """Parse Tempo ring HTML/text into structured member + state data."""
        states: Dict[str, int] = {}
        member_count = 0

        td_values = re.findall(r"<td[^>]*>([^<]+)</td>", text, re.IGNORECASE)
        known_states = {"ACTIVE", "LEAVING", "PENDING", "JOINING", "LEFT", "INACTIVE", "UNHEALTHY"}
        for val in td_values:
            val = val.strip().upper()
            if val in known_states:
                states[val] = states.get(val, 0) + 1
                member_count += 1

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
            "joining": states.get("JOINING", 0),
            "inactive": states.get("INACTIVE", 0),
            "unhealthy": states.get("UNHEALTHY", 0),
            "states": states if states else None,
            "parse_note": (
                None if states else
                "Could not extract member states from ring response."
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
        """Combine health + buildinfo + status + safe config facts for a backend profile."""
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

        build_info = None
        try:
            build_info = await self.get_build_info(backend_id)
            result["build_info"] = build_info
            data = build_info.get("data", build_info)
            result["version"] = data.get("version")
        except Exception:
            pass

        services = None
        try:
            services = await self.get_status_services(backend_id)
            result["services"] = services
        except Exception:
            pass

        config_facts = await self.get_safe_status_config(backend_id)
        if config_facts:
            result["config_facts"] = config_facts

        major, arch_gen = self.detect_tempo_generation(build_info, services, config_facts)
        result["tempo_major_version"] = major
        result["architecture_generation"] = arch_gen

        if backend.multi_tenant or config_facts.get("multitenancy_enabled"):
            result["tenant_requirements"] = "required"
        else:
            result["tenant_requirements"] = "not_applicable"

        caps = ["search", "trace_by_id"]
        try:
            endpoints = await self.get_status_endpoints(backend_id)
            if endpoints:
                caps.append("schema_discovery")
        except Exception:
            pass
        mg_procs = config_facts.get("metrics_generator_processors")
        if mg_procs is None or "local-blocks" in mg_procs:
            caps.append("traceql_metrics")
        if config_facts.get("user_configurable_overrides_enabled"):
            caps.append("tenant_overrides")
        result["capabilities"] = caps

        return result

    def add_backend(self, backend: BackendConfig) -> None:
        """Dynamically add a backend (used by K8s discovery)."""
        self._backends[backend.id] = backend

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    async def query_prometheus_service_graphs(
        self,
        backend_id: str,
        window: str,
        focus_service: Optional[str] = None,
        tenant: Optional[str] = None,
    ) -> tuple[set[str], List[Dict[str, Any]]]:
        """Query precomputed Prometheus service-graph series when prometheus_url is configured."""
        nodes: set[str] = set()
        edges: List[Dict[str, Any]] = []
        b_cfg = self._get_backend(backend_id)
        prom_url = b_cfg.prometheus_url
        if prom_url is None and backend_id == self.get_default_backend_id():
            prom_url = self._config.prometheus_url
        if not prom_url:
            return nodes, edges

        win = window if window and window[-1] in "smhd" else "5m"
        async with httpx.AsyncClient(base_url=prom_url.rstrip("/"), timeout=8.0) as client:
            matchers = [f'tenant="{tenant}"'] if tenant else []
            for attempt_matchers in ([matchers, []] if matchers else [[]]):
                sel = "{" + ",".join(attempt_matchers) + "}" if attempt_matchers else ""
                req_expr = (
                    f"sum by (client, server, connection_type) "
                    f"(rate(traces_service_graph_request_total{sel}[{win}]))"
                )
                fail_expr = (
                    f"sum by (client, server) "
                    f"(rate(traces_service_graph_request_failed_total{sel}[{win}]))"
                )
                r_req = await client.get("/api/v1/query", params={"query": req_expr})
                r_req.raise_for_status()
                req_series = (r_req.json().get("data") or {}).get("result") or []
                if not req_series:
                    continue

                fail_map: Dict[tuple[str, str], float] = {}
                try:
                    r_fail = await client.get("/api/v1/query", params={"query": fail_expr})
                    if r_fail.status_code == 200:
                        for item in (r_fail.json().get("data") or {}).get("result") or []:
                            m = item.get("metric") or {}
                            c_s, s_s = m.get("client", ""), m.get("server", "")
                            v = float((item.get("value") or [0, "0"])[1])
                            if c_s and s_s:
                                fail_map[(c_s, s_s)] = fail_map.get((c_s, s_s), 0.0) + v
                except Exception:
                    pass

                edge_agg: Dict[tuple[str, str], Dict[str, Any]] = {}
                for item in req_series:
                    m = item.get("metric") or {}
                    c_svc = m.get("client", "")
                    s_svc = m.get("server", "")
                    conn_type = m.get("connection_type")
                    try:
                        rate_val = float((item.get("value") or [0, "0"])[1])
                    except (ValueError, TypeError, IndexError):
                        rate_val = 0.0
                    if not c_svc or not s_svc:
                        continue
                    if focus_service and focus_service not in (c_svc, s_svc):
                        continue
                    nodes.add(c_svc)
                    nodes.add(s_svc)
                    entry = edge_agg.setdefault(
                        (c_svc, s_svc),
                        {"call_rate": 0.0, "connection_type": conn_type},
                    )
                    entry["call_rate"] += rate_val

                for (c_svc, s_svc), st in sorted(edge_agg.items()):
                    c_rate = round(st["call_rate"], 4)
                    e_rate = round(fail_map.get((c_svc, s_svc), 0.0), 4)
                    f_ratio = round(e_rate / c_rate, 4) if c_rate > 0 else 0.0
                    edge_obj: Dict[str, Any] = {
                        "client": c_svc,
                        "server": s_svc,
                        "call_rate": c_rate,
                        "request_rate": c_rate,
                        "error_rate": e_rate,
                        "failure_ratio": f_ratio,
                        "source": "prometheus",
                    }
                    if st.get("connection_type"):
                        edge_obj["connection_type"] = st["connection_type"]
                    edges.append(edge_obj)
                if edges:
                    break

        return nodes, edges
