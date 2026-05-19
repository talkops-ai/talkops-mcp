"""Prometheus HTTP API client service.

Async HTTP client wrapping the Prometheus HTTP API.
Handles multi-backend routing, authentication, request construction,
and response parsing into Pydantic models.
"""

import json
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from prometheus_mcp_server.config import BackendConfig, ServerConfig
from prometheus_mcp_server.models.backend import BackendCapabilities, BackendInfo
from prometheus_mcp_server.models.metadata import (
    CardinalityOverview,
    CardinalitySummary,
    MetricCatalog,
    MetricMetadata,
    RuntimeConfig,
    TopCardinalityMetric,
)
from prometheus_mcp_server.models.query import (
    DownsamplingMetadata,
    InstantQueryResult,
    InstantSample,
    LabelTopologyResult,
    RangeQueryResult,
    RangeSeries,
    ValidatePromQLResult,
)
from prometheus_mcp_server.models.target import (
    FailedTarget,
    FailedTargetsSummary,
    ServiceInfo,
    ServiceMetricsList,
    ServiceTopology,
)



class ApiError(Exception):
    """Raised for non-2xx responses from Prometheus API."""

    def __init__(self, status_code: int, message: str, body: Optional[str] = None) -> None:
        super().__init__(f"Prometheus API error {status_code}: {message}")
        self.status_code = status_code
        self.body = body


class PrometheusService:
    """Async wrapper around the Prometheus HTTP API.

    Responsibilities:
    - Route requests to the correct backend by backend_id
    - Inject Authorization headers based on backend config
    - Parse JSON into Pydantic models
    - Raise typed ApiError for non-2xx responses
    - Provide downsampling and semantic PromQL enforcement
    """

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._backends: Dict[str, BackendConfig] = {
            b.id: b for b in config.backends
        }
        self._clients: Dict[str, httpx.AsyncClient] = {}

    def _get_backend(self, backend_id: str) -> BackendConfig:
        """Resolve a backend by ID."""
        backend = self._backends.get(backend_id)
        if not backend:
            available = list(self._backends.keys())
            raise ValueError(
                f"Unknown backend_id '{backend_id}'. Available backends: {available}"
            )
        return backend

    def _ensure_client(self, backend_id: str) -> httpx.AsyncClient:
        """Lazily create an HTTP client per backend."""
        if backend_id not in self._clients or self._clients[backend_id].is_closed:
            backend = self._get_backend(backend_id)
            self._clients[backend_id] = httpx.AsyncClient(
                base_url=backend.base_url.rstrip("/"),
                verify=backend.verify_ssl,
                timeout=backend.timeout,
            )
        return self._clients[backend_id]

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()

    # ---- JSON Parsing ----

    def _parse_json(self, resp: httpx.Response, context: str = "") -> Any:
        """Safely parse a JSON response body."""
        if not resp.content:
            return {}
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raw_preview = (resp.text or "(empty)")[:500]
            raise ApiError(
                resp.status_code,
                f"Non-JSON response{f' ({context})' if context else ''}: {exc}",
                raw_preview,
            )

    # ---- Request Helper ----

    def _headers(self, backend: BackendConfig) -> Dict[str, str]:
        """Build request headers with auth."""
        headers: Dict[str, str] = {"Accept": "application/json"}
        if backend.auth_header:
            headers["Authorization"] = backend.auth_header
        return headers

    async def _request(
        self,
        method: str,
        backend_id: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request against a backend."""
        backend = self._get_backend(backend_id)
        client = self._ensure_client(backend_id)
        headers = self._headers(backend)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        resp = await client.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise ApiError(resp.status_code, resp.reason_phrase or "Error", resp.text)
        return resp

    def _validate_prom_response(self, data: Dict[str, Any], context: str = "") -> Dict[str, Any]:
        """Validate Prometheus API response has status=success."""
        if data.get("status") != "success":
            error_type = data.get("errorType", "unknown")
            error_msg = data.get("error", "Unknown error")
            raise ApiError(
                422,
                f"Prometheus error ({context}): {error_type} - {error_msg}",
            )
        return data

    # ---- Backend Discovery ----

    def list_backends(self) -> List[BackendInfo]:
        """List all configured backends."""
        return [
            BackendInfo(
                id=b.id,
                type=b.type,
                display_name=b.display_name or b.id,
                base_url=b.base_url,
                labels=b.labels,
                health="unknown",
            )
            for b in self._backends.values()
        ]

    async def check_health(self, backend_id: str) -> str:
        """Check backend health status."""
        try:
            resp = await self._request("GET", backend_id, "/-/healthy")
            if resp.status_code == 200:
                return "healthy"
            return "degraded"
        except Exception:
            return "unhealthy"

    async def get_backend_capabilities(self, backend_id: str) -> BackendCapabilities:
        """Get detailed backend capabilities and runtime info."""
        backend = self._get_backend(backend_id)
        health = await self.check_health(backend_id)

        runtimeinfo: Dict[str, Any] = {}
        features: Dict[str, bool] = {}
        version: Optional[str] = None

        try:
            resp = await self._request("GET", backend_id, "/api/v1/status/runtimeinfo")
            data = self._parse_json(resp, "runtime info")
            self._validate_prom_response(data, "runtime info")
            runtimeinfo = data.get("data", {})
        except Exception:
            pass

        try:
            resp = await self._request("GET", backend_id, "/api/v1/status/buildinfo")
            data = self._parse_json(resp, "build info")
            if data.get("status") == "success":
                version = data.get("data", {}).get("version")
        except Exception:
            pass

        return BackendCapabilities(
            backend=BackendInfo(
                id=backend.id,
                type=backend.type,
                display_name=backend.display_name or backend.id,
                base_url=backend.base_url,
                labels=backend.labels,
                health=health,  # type: ignore[arg-type]
                version=version,
            ),
            runtimeinfo=runtimeinfo,
            features=features,
        )

    # ---- Query APIs ----

    async def instant_query(
        self,
        backend_id: str,
        query: str,
        ts: Optional[float] = None,
        timeout: Optional[str] = None,
    ) -> InstantQueryResult:
        """Execute a PromQL instant query."""
        params: Dict[str, Any] = {"query": query}
        if ts is not None:
            params["time"] = ts
        if timeout:
            params["timeout"] = timeout

        start_eval = time.time()
        resp = await self._request("GET", backend_id, "/api/v1/query", params=params)
        eval_time = time.time() - start_eval

        data = self._parse_json(resp, "instant query")
        self._validate_prom_response(data, "instant query")

        payload = data.get("data", {})
        r_type = payload.get("resultType", "vector")
        raw_result = payload.get("result", [])

        samples: List[InstantSample] = []
        for item in raw_result:
            samples.append(
                InstantSample(
                    metric=item.get("metric", {}),
                    value=tuple(item.get("value", [0, "0"])),  # type: ignore[arg-type]
                )
            )

        return InstantQueryResult(
            resultType=r_type,
            result=samples,
            eval_time_seconds=eval_time,
            sample_count=len(samples),
        )

    async def range_query(
        self,
        backend_id: str,
        query: str,
        start: float,
        end: float,
        step: str,
        max_points_per_series: int = 200,
        timeout: Optional[str] = None,
    ) -> RangeQueryResult:
        """Execute a PromQL range query with mandatory downsampling."""
        params: Dict[str, Any] = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }
        if timeout:
            params["timeout"] = timeout

        resp = await self._request("GET", backend_id, "/api/v1/query_range", params=params)
        data = self._parse_json(resp, "range query")
        self._validate_prom_response(data, "range query")

        payload = data.get("data", {})
        raw_result = payload.get("result", [])

        out_series: List[RangeSeries] = []
        total_original = 0
        total_downsampled = 0

        for item in raw_result:
            metric = item.get("metric", {})
            raw_vals = item.get("values", [])
            parsed_vals: List[Tuple[float, float]] = [
                (float(ts), float(v)) for ts, v in raw_vals
            ]
            total_original += len(parsed_vals)

            ds = self._downsample_series(parsed_vals, max_points_per_series)
            total_downsampled += len(ds)

            out_series.append(
                RangeSeries(
                    metric=metric,
                    values=[(ts, str(v)) for ts, v in ds],
                )
            )

        downsampling = DownsamplingMetadata(
            strategy="average",
            original_step=step,
            effective_step=step,
            max_points_per_series=max_points_per_series,
            original_point_count=total_original,
            downsampled_point_count=total_downsampled,
        )

        return RangeQueryResult(series=out_series, downsampling=downsampling)

    async def validate_query(self, backend_id: str, query: str) -> ValidatePromQLResult:
        """Validate PromQL syntax by parsing it server-side."""
        q = query.strip()
        if not q:
            return ValidatePromQLResult(valid=False, errors=["Query is empty"])

        # Use the Prometheus /api/v1/query endpoint with a dry-run approach:
        # Execute at time=0 with a short timeout to validate syntax
        try:
            resp = await self._request(
                "GET", backend_id, "/api/v1/query",
                params={"query": q, "time": "0", "timeout": "1ms"},
            )
            return ValidatePromQLResult(valid=True)
        except ApiError as e:
            body = e.body or ""
            if "parse error" in body.lower() or "bad_data" in body.lower():
                return ValidatePromQLResult(valid=False, errors=[str(e)])
            # Timeout or execution errors mean syntax is valid but query failed
            return ValidatePromQLResult(valid=True, warnings=[str(e)])

    async def explore_label_topology(
        self, backend_id: str, metric_name: str
    ) -> LabelTopologyResult:
        """Discover label names and values for a given metric."""
        # Get label names for the specific metric using series match
        resp = await self._request(
            "GET", backend_id, "/api/v1/labels",
            params={"match[]": f'{metric_name}'},
        )
        data = self._parse_json(resp, "labels")
        self._validate_prom_response(data, "labels")
        label_names: List[str] = data.get("data", [])

        # Get values for each label (limited to this metric's series)
        label_values: Dict[str, List[str]] = {}
        for name in label_names:
            if name == "__name__":
                continue
            try:
                resp = await self._request(
                    "GET", backend_id, f"/api/v1/label/{name}/values",
                    params={"match[]": f'{metric_name}'},
                )
                lv_data = self._parse_json(resp, f"label values for {name}")
                if lv_data.get("status") == "success":
                    label_values[name] = lv_data.get("data", [])
            except Exception:
                continue

        return LabelTopologyResult(
            metric_name=metric_name,
            label_names=label_names,
            label_values=label_values,
        )

    # ---- Metadata APIs ----

    async def get_metadata(self, backend_id: str) -> Dict[str, Any]:
        """Get all metric metadata from /api/v1/metadata."""
        resp = await self._request("GET", backend_id, "/api/v1/metadata")
        data = self._parse_json(resp, "metadata")
        self._validate_prom_response(data, "metadata")
        return data.get("data", {})

    async def get_metric_catalog(self, backend_id: str) -> MetricCatalog:
        """Get a catalog of all metrics with type and help text."""
        raw_metadata = await self.get_metadata(backend_id)
        metrics: List[MetricMetadata] = []
        for name, entries in raw_metadata.items():
            if entries and isinstance(entries, list):
                entry = entries[0]
                metrics.append(
                    MetricMetadata(
                        name=name,
                        type=entry.get("type", "unknown"),
                        help=entry.get("help"),
                        unit=entry.get("unit"),
                    )
                )
        return MetricCatalog(metrics=metrics, total_count=len(metrics))

    async def get_targets(self, backend_id: str) -> Dict[str, Any]:
        """Get all scrape targets from /api/v1/targets."""
        resp = await self._request("GET", backend_id, "/api/v1/targets")
        data = self._parse_json(resp, "targets")
        self._validate_prom_response(data, "targets")
        return data.get("data", {})

    async def get_service_topology(self, backend_id: str) -> ServiceTopology:
        """Build a logical service catalog from scrape targets."""
        targets_data = await self.get_targets(backend_id)
        active_targets = targets_data.get("activeTargets", [])

        # Group targets by job
        job_targets: Dict[str, List[Dict[str, Any]]] = {}
        for target in active_targets:
            job = target.get("labels", {}).get("job", "unknown")
            if job not in job_targets:
                job_targets[job] = []
            job_targets[job].append(target)

        services: List[ServiceInfo] = []
        for job, targets in job_targets.items():
            up_count = sum(1 for t in targets if t.get("health") == "up")
            labels = targets[0].get("labels", {}) if targets else {}
            services.append(
                ServiceInfo(
                    service_id=f"{backend_id}/{job}",
                    display_name=job,
                    backend_id=backend_id,
                    job=job,
                    namespace=labels.get("namespace"),
                    environment=labels.get("environment"),
                    labels=labels,
                    targets_up=up_count,
                    targets_total=len(targets),
                )
            )

        return ServiceTopology(services=services)

    async def get_failed_targets(self, backend_id: str) -> FailedTargetsSummary:
        """Get all failed/down scrape targets."""
        targets_data = await self.get_targets(backend_id)
        active_targets = targets_data.get("activeTargets", [])

        failed: List[FailedTarget] = []
        for target in active_targets:
            if target.get("health") != "up":
                labels = target.get("labels", {})
                failed.append(
                    FailedTarget(
                        backend_id=backend_id,
                        job=labels.get("job", "unknown"),
                        instance=labels.get("instance", "unknown"),
                        last_scrape=None,
                        last_scrape_error=target.get("lastError"),
                        health=target.get("health", "down"),
                    )
                )

        return FailedTargetsSummary(failed_targets=failed)

    async def get_service_metrics(self, backend_id: str, job: str) -> ServiceMetricsList:
        """Get metrics emitted by a specific service/job via /api/v1/targets/metadata.

        Uses the Prometheus targets metadata API filtered by match_target
        to return only the metrics that a specific scrape job exposes.
        """
        resp = await self._request(
            "GET", backend_id, "/api/v1/targets/metadata",
            params={"match_target": f'{{job="{job}"}}'},
        )
        data = self._parse_json(resp, "targets/metadata")
        self._validate_prom_response(data, "targets/metadata")

        raw_entries = data.get("data", [])

        # Deduplicate: multiple targets under the same job may report
        # the same metric name. Keep one entry per unique metric name.
        seen: Dict[str, MetricMetadata] = {}
        for entry in raw_entries:
            name = entry.get("metric", "")
            if name and name not in seen:
                seen[name] = MetricMetadata(
                    name=name,
                    type=entry.get("type", "unknown"),
                    help=entry.get("help"),
                    unit=entry.get("unit"),
                )

        metrics = sorted(seen.values(), key=lambda m: m.name)
        return ServiceMetricsList(
            job=job,
            backend_id=backend_id,
            metrics=metrics,
            total_count=len(metrics),
        )

    async def get_config(self, backend_id: str) -> RuntimeConfig:
        """Get sanitized runtime configuration."""
        try:
            resp = await self._request("GET", backend_id, "/api/v1/status/config")
            data = self._parse_json(resp, "config")
            self._validate_prom_response(data, "config")
            raw_yaml = data.get("data", {}).get("yaml", "")

            # Parse key config values from the YAML string
            global_config: Dict[str, str] = {}
            scrape_match = re.search(r'scrape_interval:\s*(\S+)', raw_yaml)
            if scrape_match:
                global_config["scrape_interval"] = scrape_match.group(1)
            eval_match = re.search(r'evaluation_interval:\s*(\S+)', raw_yaml)
            if eval_match:
                global_config["evaluation_interval"] = eval_match.group(1)

        except Exception:
            global_config = {}

        # Get TSDB status
        tsdb: Dict[str, object] = {}
        try:
            resp = await self._request("GET", backend_id, "/api/v1/status/tsdb")
            tsdb_data = self._parse_json(resp, "tsdb status")
            if tsdb_data.get("status") == "success":
                tsdb = tsdb_data.get("data", {})
        except Exception:
            pass

        return RuntimeConfig(
            global_config=global_config,
            tsdb=tsdb,
        )

    async def get_cardinality_summary(self, backend_id: str) -> CardinalitySummary:
        """Get TSDB cardinality overview and top-N high-cardinality metrics."""
        resp = await self._request("GET", backend_id, "/api/v1/status/tsdb")
        data = self._parse_json(resp, "tsdb status")
        self._validate_prom_response(data, "tsdb status")

        tsdb_data = data.get("data", {})
        head_stats = tsdb_data.get("headStats", {})

        overview = CardinalityOverview(
            total_series=head_stats.get("numSeries", 0),
            head_series=head_stats.get("numSeries", 0),
            num_label_pairs=head_stats.get("numLabelPairs", 0),
            memory_bytes=head_stats.get("chunkCount", 0) * 128,  # rough estimate
        )

        # Extract top cardinality metrics from seriesCountByMetricName
        top_metrics: List[TopCardinalityMetric] = []
        series_by_metric = tsdb_data.get("seriesCountByMetricName", [])
        for item in series_by_metric[:20]:  # Top 20
            top_metrics.append(
                TopCardinalityMetric(
                    metric_name=item.get("name", ""),
                    series_count=item.get("value", 0),
                )
            )

        return CardinalitySummary(
            overview=overview,
            top_cardinality_metrics=top_metrics,
        )

    # ---- Downsampling ----

    @staticmethod
    def _downsample_series(
        values: List[Tuple[float, float]],
        max_points: int,
    ) -> List[Tuple[float, float]]:
        """Downsample a time series to <= max_points using average-bucket strategy."""
        if len(values) <= max_points or max_points <= 0:
            return values

        bucket_size = math.ceil(len(values) / max_points)
        downsampled: List[Tuple[float, float]] = []
        for i in range(0, len(values), bucket_size):
            bucket = values[i: i + bucket_size]
            if not bucket:
                continue
            ts = bucket[-1][0]
            avg = sum(v for _, v in bucket) / len(bucket)
            downsampled.append((ts, avg))
        return downsampled

    async def enforce_counter_rule(
        self, backend_id: str, query: str, allow_raw: bool
    ) -> None:
        """Enforce semantic counter rule: counters must use rate()/increase().

        Raises ValueError if a counter is queried raw without opt-in.
        Uses metadata-aware checking to detect counter metrics even inside
        aggregation functions like sum(), avg(), topk().
        """
        if allow_raw:
            return

        q = query.strip()
        # Safe wrapper functions that properly handle counters
        safe_wrappers = {"rate", "increase", "irate", "resets", "changes"}

        # Check if the query is wrapped in a safe function at the top level
        for wrapper in safe_wrappers:
            if q.startswith(f"{wrapper}("):
                return

        try:
            metadata = await self.get_metadata(backend_id)
            # Find all counter metric names that appear in the query
            for metric_name, meta_entries in metadata.items():
                if not isinstance(meta_entries, list) or not meta_entries:
                    continue
                if meta_entries[0].get("type") != "counter":
                    continue
                # Check if this counter metric name appears in the query
                if metric_name not in q:
                    continue
                # Check if it's wrapped in a safe function anywhere in the query
                is_safe = False
                for wrapper in safe_wrappers:
                    if f"{wrapper}({metric_name}" in q or f"{wrapper}( {metric_name}" in q:
                        is_safe = True
                        break
                if not is_safe:
                    raise ValueError(
                        f"Counter metric '{metric_name}' must be wrapped in rate()/increase(). "
                        f"Example: rate({metric_name}[5m]). "
                        f"Set allow_raw_counters=true to override."
                    )
        except ValueError:
            raise
        except Exception:
            pass

    # ---- Rules Management APIs ----

    async def list_rule_groups(self, backend_id: str) -> Dict[str, Any]:
        """List all rule groups from /api/v1/rules."""
        resp = await self._request("GET", backend_id, "/api/v1/rules")
        data = self._parse_json(resp, "rules")
        self._validate_prom_response(data, "rules")
        return data.get("data", {})

    async def get_rule_group(
        self, backend_id: str, group_name: str, file_filter: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a specific rule group by name."""
        rules_data = await self.list_rule_groups(backend_id)
        for group in rules_data.get("groups", []):
            if group.get("name") == group_name:
                if file_filter and group.get("file") != file_filter:
                    continue
                return group
        return None

    async def get_alerts_for_state(
        self, backend_id: str, alert_name: str,
        start: float, end: float, step: str,
    ) -> List[Dict[str, Any]]:
        """Query ALERTS_FOR_STATE metric for firing history analysis."""
        query = f'ALERTS_FOR_STATE{{alertname="{alert_name}"}}'
        try:
            result = await self.range_query(
                backend_id, query, start, end, step,
                max_points_per_series=500,
            )
            return [s.model_dump() for s in result.series]
        except Exception:
            return []

    async def evaluate_rule_expr(
        self, backend_id: str, expr: str,
        start: float, end: float, step: str,
    ) -> List[Dict[str, Any]]:
        """Evaluate a rule expression over a time range for simulation."""
        try:
            result = await self.range_query(
                backend_id, expr, start, end, step,
                max_points_per_series=500,
            )
            return [s.model_dump() for s in result.series]
        except Exception:
            return []

    async def get_label_values_for_metric(
        self, backend_id: str, metric_name: str
    ) -> Dict[str, List[str]]:
        """Get all label values for a specific metric."""
        topology = await self.explore_label_topology(backend_id, metric_name)
        return topology.label_values

