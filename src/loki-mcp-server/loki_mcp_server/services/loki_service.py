"""Core HTTP client for the Grafana Loki API.

This service provides the lowest-level interface to Loki's
HTTP endpoints. All methods return parsed JSON dicts —
tools and resources shape the output into domain models.

Includes retry with exponential backoff, connection pool limits,
and X-Request-ID injection for backend log correlation.

API Reference: https://grafana.com/docs/loki/latest/reference/loki-http-api/
"""

import asyncio
import base64
import uuid
from typing import Any, Dict, List, Optional

import httpx

from loki_mcp_server.config import AuthConfig, LokiConfig
from loki_mcp_server.exceptions import (
    LokiConnectionError,
    LokiQueryError,
    LokiResourceNotFoundError,
)


class LokiService:
    """HTTP client for Grafana Loki's REST API.

    All methods map 1:1 to Loki HTTP API endpoints.
    Uses httpx.AsyncClient with connection pooling and retry/backoff.
    Always reads data["data"] from Loki's response envelope.

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
            "User-Agent": "TalkOps-Loki-MCP/0.1.0",
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
                delay = LokiService._RETRY_BASE_DELAY * (2 ** attempt)
        else:
            delay = min(LokiService._RETRY_BASE_DELAY * (2 ** attempt), 8.0)
        await asyncio.sleep(delay)

    async def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Low-level GET with retry/backoff — single source of truth.

        Retries up to _MAX_RETRIES times for 429/502/503/504 and transient
        connection errors, using exponential backoff. Respects Retry-After.

        Args:
            url: Fully-qualified URL to request.
            params: Query parameters.

        Returns:
            Raw httpx.Response (caller decides how to interpret it).

        Raises:
            LokiConnectionError: Network/timeout failures after retries.
            LokiQueryError: Loki returned a non-retryable HTTP error.
            LokiResourceNotFoundError: Loki returned 404.
        """
        client = await self._get_client()
        request_id = str(uuid.uuid4())

        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                req_headers = {"X-Request-ID": request_id}
                if headers:
                    req_headers.update(headers)
                
                resp = await client.get(
                    url,
                    params=params or {},
                    headers=req_headers,
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
                if status in self._RETRYABLE_STATUSES and attempt < self._MAX_RETRIES:
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

        raise last_exc  # unreachable, satisfies type checker

    async def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        require_status: bool = True,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET a Loki API endpoint and return parsed JSON.

        Thin wrapper over _request_with_retry that handles JSON
        parsing and optional {"status": "success"} envelope validation.

        Args:
            path: API path relative to /loki/api/v1/ (e.g., 'labels').
            params: Query parameters.
            require_status: If True, validate the {status: "success"}
                envelope. Set to False for endpoints that return
                raw JSON without the standard envelope (e.g.,
                /detected_fields, /index/stats).

        Returns:
            Parsed JSON response.

        Raises:
            LokiConnectionError: If the request fails after retries.
            LokiQueryError: If Loki returns an error.
        """
        url = f"{self._base_url}/loki/api/v1/{path.strip('/')}"
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        resp = await self._request_with_retry(url, params, headers=headers)

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
        """GET a non-API endpoint and return the raw response.

        Thin wrapper over _request_with_retry for non-JSON
        endpoints (e.g., /ready, /metrics).

        Args:
            path: Path relative to base URL (e.g., 'ready').
            params: Query parameters.

        Returns:
            Raw httpx.Response.
        """
        url = f"{self._base_url}/{path.strip('/')}"
        headers = {"X-Scope-OrgID": org_id} if org_id else None
        return await self._request_with_retry(url, params, headers=headers)

    def _require_success(self, data: Dict[str, Any], url: str) -> None:
        """Validate that Loki's response envelope indicates success.

        Loki returns {"status": "success", "data": ...} for OK responses.

        Args:
            data: Parsed JSON response from Loki.
            url: Request URL for error context.

        Raises:
            LokiQueryError: If status is not 'success'.
        """
        if data.get("status") != "success":
            raise LokiQueryError(
                f"Loki API error for {url}: {data}"
            )

    # ──────────────────────────────────────────────
    # Schema & Discovery
    # ──────────────────────────────────────────────

    async def get_labels(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> List[str]:
        """Get all label names from Loki.

        GET /loki/api/v1/labels

        Args:
            start: Optional start timestamp.
            end: Optional end timestamp.

        Returns:
            List of label name strings.
        """
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
        """Get values for a specific label.

        GET /loki/api/v1/label/{name}/values

        Args:
            label: Label name.
            query: Optional LogQL stream selector to scope values.
            start: Optional start timestamp.
            end: Optional end timestamp.

        Returns:
            List of label value strings.
        """
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
        """Get all series matching a label matcher.

        GET /loki/api/v1/series

        Args:
            match: LogQL label matcher (e.g., '{app="checkout"}').
            start: Optional start timestamp.
            end: Optional end timestamp.

        Returns:
            List of label-value dicts for each matching series.
        """
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
        """Execute a LogQL query over a time range (log or metric).

        GET /loki/api/v1/query_range

        Args:
            query: LogQL query string.
            start: Start timestamp.
            end: End timestamp.
            limit: Maximum log lines (for stream results).
            direction: 'forward' or 'backward' (for stream results).
            step: Step duration for metric queries (e.g., '30s', '5m').
                Auto-computed by Loki if omitted.

        Returns:
            Raw response data dict with 'resultType' and 'result'.
        """
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
    ) -> Dict[str, Any]:
        """Execute an instant LogQL query.

        GET /loki/api/v1/query

        Args:
            query: LogQL query string.
            time: Optional evaluation timestamp.

        Returns:
            Raw response data dict.
        """
        params: Dict[str, Any] = {"query": query}
        if time:
            params["time"] = time

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
        """Execute a LogQL metric query (rate/count_over_time/etc.).

        GET /loki/api/v1/query_range

        Uses the same endpoint as query_range but expects metric
        results (resultType: matrix or vector).

        Args:
            query: LogQL metric query string.
            start: Start timestamp.
            end: End timestamp.
            step: Step duration (e.g., '1m', '5m', '1h').

        Returns:
            Raw response data dict with 'resultType' and 'result'.
        """
        params: Dict[str, Any] = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }

        data = await self._get("query_range", params, org_id=org_id)
        return data.get("data", {})

    # ──────────────────────────────────────────────
    # Index Stats
    # ──────────────────────────────────────────────

    async def get_index_stats(
        self,
        query: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get index statistics for a query.

        GET /loki/api/v1/index/stats

        Args:
            query: LogQL stream selector.
            start: Optional start timestamp.
            end: Optional end timestamp.

        Returns:
            Dict with streams, chunks, entries, bytes counts.
        """
        params: Dict[str, Any] = {"query": query}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        data = await self._get("index/stats", params, require_status=False, org_id=org_id)
        return data

    # ──────────────────────────────────────────────
    # Detected Fields
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
        """Discover structured fields in log lines.

        GET /loki/api/v1/detected_fields

        Returns fields (JSON/logfmt keys, structured metadata) that
        Loki has detected in log lines matching the given selector,
        along with inferred type, estimated cardinality, and parser.

        Args:
            query: LogQL stream selector (e.g., '{app="checkout"}').
            start: Optional start timestamp.
            end: Optional end timestamp.
            line_limit: Max log lines to scan per shard (default 100).
            field_limit: Max fields to return (default 1000).

        Returns:
            Dict with 'fields' list and 'limit' value.
        """
        params: Dict[str, Any] = {"query": query}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if line_limit is not None:
            params["line_limit"] = line_limit
        if field_limit is not None:
            params["limit"] = field_limit

        data = await self._get("detected_fields", params, require_status=False, org_id=org_id)
        return data

    # ──────────────────────────────────────────────
    # Patterns
    # ──────────────────────────────────────────────

    async def get_patterns(
        self,
        query: str,
        start: str,
        end: str,
        org_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Detect log patterns for a stream.

        GET /loki/api/v1/patterns

        Requires pattern_ingester.enabled: true in Loki config.

        Args:
            query: LogQL stream selector (e.g., '{app="checkout"}').
            start: Start timestamp.
            end: End timestamp.

        Returns:
            List of pattern dicts with 'pattern' and 'samples' fields.
        """
        params: Dict[str, Any] = {
            "query": query,
            "start": start,
            "end": end,
        }

        data = await self._get("patterns", params, org_id=org_id)
        # Patterns endpoint returns data directly as a list
        return data.get("data", [])

    # ──────────────────────────────────────────────
    # Health & Status
    # ──────────────────────────────────────────────

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

        # Primary health signal: Loki's canonical /ready endpoint.
        # Call the HTTP client directly — do NOT use _get_raw() which
        # raises on non-200. We need the raw status code as the signal.
        try:
            client = await self._get_client()
            url = f"{self._base_url}/ready"
            resp = await client.get(url)

            # Any HTTP response means the server is reachable
            result["reachable"] = True
            result["ready"] = resp.status_code == 200
            result["ready_detail"] = (
                f"HTTP {resp.status_code}: {resp.text.strip()[:100]}"
            )

            # Status derived directly from /ready — the source of truth
            result["status"] = (
                "healthy" if resp.status_code == 200 else "degraded"
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            result["ready_detail"] = "Connection failed or timed out"
            result["status"] = "unhealthy"

        # Supplementary metadata: label count.
        # Best-effort enrichment — does NOT change the health status.
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
