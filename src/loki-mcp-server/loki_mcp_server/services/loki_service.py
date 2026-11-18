"""Core HTTP client for the Grafana Loki API.

This service provides the lowest-level interface to Loki's
HTTP endpoints. All methods return parsed JSON dicts or structured payloads —
tools and resources shape the output into domain responses.

Includes retry with exponential backoff, connection pool limits,
and X-Request-ID injection for backend log correlation.

API Reference: https://grafana.com/docs/loki/latest/reference/loki-http-api/
"""

import asyncio
import base64
import re
import uuid
from typing import Any, Dict, List, Optional

import httpx
import yaml

from loki_mcp_server.config import AuthConfig, LokiConfig
from loki_mcp_server.exceptions import (
    LokiConnectionError,
    LokiQueryError,
    LokiResourceNotFoundError,
)


class LokiService:
    """HTTP client for Grafana Loki's REST API.

    Uses httpx.AsyncClient with connection pooling and retry/backoff.
    Always reads data["data"] from Loki's response envelope where applicable.

    Auth modes:
    - Bearer token via Authorization header
    - Basic Auth via Authorization header
    - Multi-tenancy via X-Scope-OrgID header
    """

    # Retryable HTTP status codes
    _RETRYABLE_STATUSES = frozenset([429, 502, 503, 504])
    # Maximum number of retry attempts for transient failures
    _MAX_RETRIES = 3
    # Base delay in seconds (doubles each attempt)
    _RETRY_BASE_DELAY = 0.5

    def __init__(
        self,
        loki_config: LokiConfig,
        auth_config: AuthConfig,
    ) -> None:
        self._base_url = loki_config.base_url.rstrip("/")
        self._timeout = loki_config.timeout
        self._verify_ssl = loki_config.verify_ssl
        self._auth_config = auth_config
        self._client: Optional[httpx.AsyncClient] = None

    # ──────────────────────────────────────────────
    # HTTP Layer
    # ──────────────────────────────────────────────

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers with auth and tenancy."""
        headers: Dict[str, str] = {
            "User-Agent": "TalkOps-Loki-MCP/0.2.0",
            "Accept": "application/json",
        }

        auth = self._auth_config

        if auth.auth_token:
            headers["Authorization"] = f"Bearer {auth.auth_token}"
        elif auth.basic_auth_user and auth.basic_auth_password:
            credentials = base64.b64encode(
                f"{auth.basic_auth_user}:{auth.basic_auth_password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"

        if auth.org_id:
            headers["X-Scope-OrgID"] = auth.org_id

        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client with connection pool limits."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                verify=self._verify_ssl,
                headers=self._build_headers(),
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                ),
            )
        return self._client

    @staticmethod
    async def _backoff(attempt: int, retry_after: Optional[str]) -> None:
        """Wait before retrying, honouring Retry-After when present."""
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = LokiService._RETRY_BASE_DELAY * (2**attempt)
        else:
            delay = min(LokiService._RETRY_BASE_DELAY * (2**attempt), 8.0)
        await asyncio.sleep(delay)

    async def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        method: str = "GET",
        content: Optional[bytes | str] = None,
    ) -> httpx.Response:
        """Low-level HTTP request with retry/backoff — single source of truth."""
        client = await self._get_client()
        request_id = str(uuid.uuid4())

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                req_headers = {"X-Request-ID": request_id}
                if headers:
                    req_headers.update(headers)

                if method.upper() == "GET" and content is None:
                    resp = await client.get(
                        url,
                        params=params or {},
                        headers=req_headers,
                    )
                else:
                    resp = await client.request(
                        method.upper(),
                        url,
                        params=params or {},
                        headers=req_headers,
                        content=content,
                    )

                if resp.status_code == 404:
                    raise LokiResourceNotFoundError(
                        f"Loki endpoint not found: {url}"
                    )

                resp.raise_for_status()
                return resp

            except httpx.ConnectError as exc:
                last_exc = LokiConnectionError(
                    f"Cannot connect to Loki at {self._base_url}: {exc}"
                )
                if attempt < self._MAX_RETRIES:
                    await self._backoff(attempt, None)
                    continue
                raise last_exc from exc
            except httpx.TimeoutException as exc:
                last_exc = LokiConnectionError(
                    f"Loki request timed out ({self._timeout}s): {url}"
                )
                if attempt < self._MAX_RETRIES:
                    await self._backoff(attempt, None)
                    continue
                raise last_exc from exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:500]
                if status == 400:
                    raise LokiQueryError(
                        f"Loki bad request (400) for {url}: {body}"
                    ) from exc
                if (
                    status in self._RETRYABLE_STATUSES
                    and attempt < self._MAX_RETRIES
                ):
                    retry_after = exc.response.headers.get("Retry-After")
                    await self._backoff(attempt, retry_after)
                    continue
                if status == 429:
                    raise LokiQueryError(
                        f"Rate limited (429) by Loki after "
                        f"{attempt + 1} attempt(s)"
                    ) from exc
                raise LokiQueryError(
                    f"Loki HTTP error {status} for {url}: {body}"
                ) from exc

        raise last_exc  # unreachable

    async def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        require_status: bool = True,
        org_id: Optional[str] = None,
        **extra_params: Any,
    ) -> Dict[str, Any]:
        """GET a Loki API endpoint and return parsed JSON."""
        url = f"{self._base_url}/loki/api/v1/{path.strip('/')}"
        merged_params: Dict[str, Any] = {}
        if params:
            merged_params.update(params)
        if extra_params:
            merged_params.update(extra_params)
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        resp = await self._request_with_retry(url, merged_params, headers=headers)

        data = resp.json()
        if require_status:
            self._require_success(data, url)
        return data

    async def _get_raw(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        org_id: Optional[str] = None,
    ) -> httpx.Response:
        """GET a non-API endpoint and return the raw response."""
        url = f"{self._base_url}/{path.strip('/')}"
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        return await self._request_with_retry(url, params, headers=headers)

    def _require_success(self, data: Dict[str, Any], url: str) -> None:
        """Validate that Loki's response envelope indicates success."""
        if data.get("status") != "success":
            raise LokiQueryError(f"Loki API error for {url}: {data}")

    # ──────────────────────────────────────────────
    # Schema & Discovery
    # ──────────────────────────────────────────────

    async def get_labels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> List[str]:
        """Get all label names from Loki (`GET /loki/api/v1/labels`)."""
        params: Dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        data = await self._get("labels", params, org_id=org_id)
        return data.get("data", [])

    async def get_label_values(
        self,
        label: str,
        query: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> List[str]:
        """Get values for a specific label (`GET /loki/api/v1/label/{name}/values`)."""
        params: Dict[str, Any] = {}
        if query:
            params["query"] = query
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        data = await self._get(f"label/{label}/values", params, org_id=org_id)
        return data.get("data", [])

    async def get_series(
        self,
        match: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Get all series matching a label matcher (`GET /loki/api/v1/series`)."""
        params: Dict[str, Any] = {"match[]": match}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        data = await self._get("series", params, org_id=org_id)
        return data.get("data", [])

    # ──────────────────────────────────────────────
    # Query & Execution
    # ──────────────────────────────────────────────

    async def query_range(
        self,
        query: str,
        start: str,
        end: str,
        limit: int = 1000,
        direction: Optional[str] = "backward",
        step: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a LogQL query over a time range (`GET /loki/api/v1/query_range`)."""
        params: Dict[str, Any] = {
            "query": query,
            "start": start,
            "end": end,
            "limit": limit,
        }
        if direction:
            params["direction"] = direction
        if step:
            params["step"] = step

        data = await self._get("query_range", params, org_id=org_id)
        return data.get("data", {})

    async def query_instant(
        self,
        query: str,
        time: Optional[str] = None,
        org_id: Optional[str] = None,
        **extra_params: Any,
    ) -> Dict[str, Any]:
        """Execute an instant LogQL query (`GET /loki/api/v1/query`)."""
        params: Dict[str, Any] = {"query": query}
        if time:
            params["time"] = time
        if extra_params:
            params.update(extra_params)

        data = await self._get("query", params, org_id=org_id)
        return data.get("data", {})

    async def query_range_metrics(
        self,
        query: str,
        start: str,
        end: str,
        step: str = "1m",
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a LogQL metric query (`GET /loki/api/v1/query_range`)."""
        params: Dict[str, Any] = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }

        data = await self._get("query_range", params, org_id=org_id)
        return data.get("data", {})

    # ──────────────────────────────────────────────
    # Index Stats & Volume (FinOps)
    # ──────────────────────────────────────────────

    async def get_index_stats(
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get index statistics for a query (`GET /loki/api/v1/index/stats`)."""
        from loki_mcp_server.utils.logql_helpers import extract_stream_selector_for_stats

        params: Dict[str, Any] = {"query": query}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        try:
            data = await self._get(
                "index/stats", params, require_status=False, org_id=org_id
            )
            return data
        except LokiQueryError:
            fallback_sel = extract_stream_selector_for_stats(query)
            if fallback_sel and fallback_sel != query:
                params["query"] = fallback_sel
                return await self._get(
                    "index/stats", params, require_status=False, org_id=org_id
                )
            raise

    async def get_index_volume(
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 20,
        target_labels: Optional[str] = None,
        aggregate_by: str = "labels",
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query TSDB index volume (`GET /loki/api/v1/index/volume`).

        Requires `limits_config.volume_enabled: true` in Loki.
        """
        params: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "aggregateBy": aggregate_by,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if target_labels:
            params["targetLabels"] = target_labels

        data = await self._get(
            "index/volume", params, require_status=False, org_id=org_id
        )
        return data.get("data", data)

    # ──────────────────────────────────────────────
    # Detected Fields, Detected Labels & Patterns
    # ──────────────────────────────────────────────

    async def get_detected_fields(
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        line_limit: Optional[int] = None,
        field_limit: Optional[int] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discover structured fields (`GET /loki/api/v1/detected_fields`)."""
        params: Dict[str, Any] = {"query": query}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if line_limit is not None:
            params["line_limit"] = line_limit
        if field_limit is not None:
            params["limit"] = field_limit

        data = await self._get(
            "detected_fields", params, require_status=False, org_id=org_id
        )
        return data

    async def get_detected_labels(
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discover detected labels and cardinality (`GET /loki/api/v1/detected_labels`)."""
        params: Dict[str, Any] = {"query": query}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        return await self._get(
            "detected_labels", params, require_status=False, org_id=org_id
        )

    async def get_patterns(
        self,
        query: str,
        start: str,
        end: str,
        org_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Detect log patterns for a stream (`GET /loki/api/v1/patterns`)."""
        params: Dict[str, Any] = {
            "query": query,
            "start": start,
            "end": end,
        }

        data = await self._get("patterns", params, org_id=org_id)
        return data.get("data", [])

    # ──────────────────────────────────────────────
    # Loki Ruler API (/loki/api/v1/rules)
    # ──────────────────────────────────────────────

    async def get_rules(
        self,
        namespace: Optional[str] = None,
        group_name: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch Loki Ruler alerting & recording rules (`GET /loki/api/v1/rules`)."""
        path = "rules"
        if namespace:
            path = f"{path}/{namespace}"
            if group_name:
                path = f"{path}/{group_name}"

        url = f"{self._base_url}/loki/api/v1/{path}"
        headers = {"Accept": "application/yaml, application/json"}
        if org_id:
            headers["X-Scope-OrgID"] = org_id

        try:
            resp = await self._request_with_retry(url, headers=headers)
        except LokiResourceNotFoundError:
            return {}
        except LokiQueryError as exc:
            err_lower = str(exc).lower()
            if (
                "no rule groups found" in err_lower
                or "no such file or directory" in err_lower
                or "group does not exist" in err_lower
            ):
                return {}
            raise

        text = resp.text.strip()
        if not text or text == "no rule groups found":
            return {}
        try:
            parsed = yaml.safe_load(text)
            if isinstance(parsed, dict):
                return parsed
            return {"groups": parsed}
        except Exception:
            return {"raw": text}

    async def upsert_rule_group(
        self,
        namespace: str,
        rules_yaml: str,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a Loki Ruler rule group (`POST /loki/api/v1/rules/{namespace}`)."""
        url = f"{self._base_url}/loki/api/v1/rules/{namespace.strip('/')}"
        headers = {"Content-Type": "application/yaml"}
        if org_id:
            headers["X-Scope-OrgID"] = org_id

        resp = await self._request_with_retry(
            url,
            headers=headers,
            method="POST",
            content=rules_yaml.encode("utf-8"),
        )
        return {
            "status": "applied",
            "http_status": resp.status_code,
            "namespace": namespace,
        }

    async def delete_rule_group(
        self,
        namespace: str,
        group_name: str,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a Loki Ruler rule group (`DELETE /loki/api/v1/rules/{namespace}/{group}`)."""
        url = (
            f"{self._base_url}/loki/api/v1/rules/"
            f"{namespace.strip('/')}/{group_name.strip('/')}"
        )
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        resp = await self._request_with_retry(
            url,
            headers=headers,
            method="DELETE",
        )
        return {
            "status": "deleted",
            "http_status": resp.status_code,
            "namespace": namespace,
            "group_name": group_name,
        }

    # ──────────────────────────────────────────────
    # Compactor Delete Requests (/loki/api/v1/delete)
    # ──────────────────────────────────────────────

    async def list_delete_requests(
        self,
        org_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List Compactor log deletion requests (`GET /loki/api/v1/delete`)."""
        url = f"{self._base_url}/loki/api/v1/delete"
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        try:
            resp = await self._request_with_retry(url, headers=headers)
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("data", [])
            return []
        except LokiResourceNotFoundError:
            return []

    async def create_delete_request(
        self,
        query: str,
        start: str,
        end: str,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a Compactor log deletion request (`POST /loki/api/v1/delete`)."""
        url = f"{self._base_url}/loki/api/v1/delete"
        params = {"query": query, "start": start, "end": end}
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        resp = await self._request_with_retry(
            url,
            params=params,
            headers=headers,
            method="POST",
        )
        return {
            "status": "submitted",
            "http_status": resp.status_code,
            "query": query,
            "start": start,
            "end": end,
        }

    async def cancel_delete_request(
        self,
        request_id: str,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel a pending Compactor delete request (`DELETE /loki/api/v1/delete`)."""
        url = f"{self._base_url}/loki/api/v1/delete"
        params = {"request_id": request_id, "force": "true"}
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        resp = await self._request_with_retry(
            url,
            params=params,
            headers=headers,
            method="DELETE",
        )
        return {
            "status": "cancelled",
            "http_status": resp.status_code,
            "request_id": request_id,
        }

    # ──────────────────────────────────────────────
    # Health, Buildinfo & Internal Metrics Diagnostics
    # ──────────────────────────────────────────────

    async def get_build_info(self) -> Dict[str, Any]:
        """Fetch Loki build version metadata (`GET /loki/api/v1/status/buildinfo`)."""
        try:
            data = await self._get("status/buildinfo", require_status=False)
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
                return data["data"]
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def get_runtime_config(self) -> Dict[str, Any]:
        """Fetch and summarize active Loki runtime config (`GET /config`)."""
        try:
            resp = await self._get_raw("config")
            parsed = yaml.safe_load(resp.text)
            if not isinstance(parsed, dict):
                return {}
            compactor = parsed.get("compactor") if isinstance(parsed.get("compactor"), dict) else {}
            limits = parsed.get("limits_config") if isinstance(parsed.get("limits_config"), dict) else {}
            pattern_ing = (
                parsed.get("pattern_ingester")
                if isinstance(parsed.get("pattern_ingester"), dict)
                else {}
            )
            ruler = parsed.get("ruler") if isinstance(parsed.get("ruler"), dict) else {}
            schema_cfgs = (
                (parsed.get("schema_config") or {}).get("configs")
                if isinstance(parsed.get("schema_config"), dict)
                else []
            )
            latest_schema = (
                schema_cfgs[-1]
                if isinstance(schema_cfgs, list) and schema_cfgs and isinstance(schema_cfgs[-1], dict)
                else {}
            )
            retention_enabled = bool(compactor.get("retention_enabled", False))
            del_store = str(compactor.get("delete_request_store") or "").strip()
            return {
                "auth_enabled": bool(parsed.get("auth_enabled", False)),
                "schema": {
                    "store": latest_schema.get("store"),
                    "schema": latest_schema.get("schema"),
                    "object_store": latest_schema.get("object_store"),
                    "from": str(latest_schema.get("from", "")),
                },
                "compactor": {
                    "retention_enabled": retention_enabled,
                    "delete_request_store": del_store or None,
                    "retention_delete_delay": compactor.get("retention_delete_delay"),
                    "compactor_delete_ready": bool(retention_enabled and del_store),
                },
                "limits_config": {
                    "allow_structured_metadata": limits.get("allow_structured_metadata"),
                    "volume_enabled": limits.get("volume_enabled"),
                    "unordered_writes": limits.get("unordered_writes"),
                    "reject_old_samples_max_age": limits.get("reject_old_samples_max_age"),
                    "retention_period": limits.get("retention_period"),
                    "ingestion_rate_mb": limits.get("ingestion_rate_mb"),
                    "ingestion_burst_size_mb": limits.get("ingestion_burst_size_mb"),
                    "per_stream_rate_limit": limits.get("per_stream_rate_limit"),
                    "max_global_streams_per_user": limits.get("max_global_streams_per_user"),
                    "max_line_size_truncate": limits.get("max_line_size_truncate"),
                },
                "pattern_ingester": {
                    "enabled": bool(pattern_ing.get("enabled", False)),
                },
                "ruler": {
                    "enable_api": bool(ruler.get("enable_api", False)),
                    "alertmanager_url": ruler.get("alertmanager_url"),
                },
            }
        except Exception:
            return {}

    async def get_discarded_samples_diagnostics(self) -> Dict[str, Any]:
        """Parse `/metrics` for `loki_discarded_samples_total` and distributor/ingester health."""
        discarded_by_reason: Dict[str, float] = {}
        ingester_chunks: Optional[float] = None
        try:
            resp = await self._get_raw("metrics")
            text = resp.text
            for line in text.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                if line.startswith("loki_discarded_samples_total"):
                    m_reason = re.search(r'reason="([^"]+)"', line)
                    m_val = re.search(r"\}\s+([0-9.eE+-]+)$", line)
                    if m_reason and m_val:
                        reason = m_reason.group(1)
                        val = float(m_val.group(1))
                        discarded_by_reason[reason] = (
                            discarded_by_reason.get(reason, 0.0) + val
                        )
                elif line.startswith("loki_ingester_memory_chunks"):
                    m_val = re.search(r"\s+([0-9.eE+-]+)$", line)
                    if m_val:
                        ingester_chunks = float(m_val.group(1))
            return {
                "metrics_scraped": True,
                "discarded_samples_by_reason": discarded_by_reason,
                "total_discarded_samples": sum(discarded_by_reason.values()),
                "ingester_memory_chunks": ingester_chunks,
            }
        except Exception:
            return {
                "metrics_scraped": False,
                "discarded_samples_by_reason": {},
                "total_discarded_samples": 0.0,
                "ingester_memory_chunks": None,
            }

    async def health_check(self) -> Dict[str, Any]:
        """Check Loki connectivity and readiness.

        Uses Loki's canonical GET /ready endpoint as the primary
        health signal. The /ready status code is the source of truth:
        - 200 → healthy (server is ready to accept traffic)
        - non-200 → degraded (reachable but not ready)
        - connection error → unhealthy (server is unreachable)

        Label count is supplementary metadata and does NOT
        override the /ready verdict.

        Returns:
            Dict with 'reachable', 'ready', 'ready_detail',
            'label_count', and 'status' fields.
        """
        result: Dict[str, Any] = {
            "reachable": False,
            "ready": False,
            "ready_detail": "",
            "label_count": 0,
            "status": "unhealthy",
        }

        try:
            client = await self._get_client()
            url = f"{self._base_url}/ready"
            resp = await client.get(url)

            result["reachable"] = True
            result["ready"] = resp.status_code == 200
            result["ready_detail"] = (
                f"HTTP {resp.status_code}: {resp.text.strip()[:100]}"
            )
            result["status"] = (
                "healthy" if resp.status_code == 200 else "degraded"
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            result["ready_detail"] = "Connection failed or timed out"
            result["status"] = "unhealthy"

        if result["reachable"]:
            try:
                labels = await self.get_labels()
                result["label_count"] = len(labels)
            except (LokiConnectionError, LokiQueryError):
                pass

        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
