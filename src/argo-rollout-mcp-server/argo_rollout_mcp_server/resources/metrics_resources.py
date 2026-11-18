"""Prometheus metrics summary and connectivity status resources."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import quote, urljoin

import requests

from argo_rollout_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


def _query_prometheus(base_url: str, query: str, timeout: float = 5.0) -> Optional[float]:
    """Execute a PromQL instant query and return the first scalar value."""
    try:
        url = urljoin(base_url.rstrip("/") + "/", f"api/v1/query?query={quote(query)}")
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            return None
        result_type = data.get("data", {}).get("resultType", "")
        result = data.get("data", {}).get("result", [])
        if not result:
            return None
        if result_type == "scalar" or (
            isinstance(result, (list, tuple))
            and len(result) >= 2
            and not isinstance(result[0], dict)
        ):
            try:
                return float(result[1])
            except (TypeError, ValueError):
                return None
        val = result[0].get("value") if isinstance(result[0], dict) else None
        if val is None:
            return None
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                return float(val[1])
            except (TypeError, ValueError):
                return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None
    except Exception as e:
        logger.debug(f"Prometheus query failed: {e}")
        return None


def _probe_prometheus(base_url: str, timeout: float = 3.0) -> bool:
    """Probe Prometheus connectivity via a simple query."""
    return _query_prometheus(base_url, "1", timeout) is not None


class MetricsResources(BaseResource):
    """Prometheus service metrics summary and connectivity status resources."""

    def _get_prometheus_url(self) -> Optional[str]:
        if not self.config:
            return None
        return getattr(self.config, "prometheus_url", None)

    def _fetch_metrics_from_prometheus(
        self, base_url: str, service: str, namespace: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch real metrics from Prometheus. Returns None if Prometheus is unreachable."""
        if not _probe_prometheus(base_url):
            return None

        svc_escaped = service.replace("\\", "\\\\").replace('"', '\\"')
        svc_re = f".*{svc_escaped}.*"

        req_rate_query = f'sum(rate(traefik_service_requests_total{{service=~"{svc_re}"}}[5m]))'
        req_rate = _query_prometheus(base_url, req_rate_query)

        err_count_query = f'sum(rate(traefik_service_requests_total{{code=~"5..",service=~"{svc_re}"}}[5m]))'
        err_count = _query_prometheus(base_url, err_count_query)
        total_count_query = f'sum(rate(traefik_service_requests_total{{service=~"{svc_re}"}}[5m]))'
        total_count = _query_prometheus(base_url, total_count_query)

        error_rate = 0.0
        if total_count is not None and total_count > 0 and err_count is not None:
            error_rate = (err_count / total_count) * 100.0

        p50 = _query_prometheus(
            base_url,
            f'histogram_quantile(0.5, sum(rate(traefik_service_request_duration_seconds_bucket{{service=~"{svc_re}"}}[5m])) by (le))',
        )
        p95 = _query_prometheus(
            base_url,
            f'histogram_quantile(0.95, sum(rate(traefik_service_request_duration_seconds_bucket{{service=~"{svc_re}"}}[5m])) by (le))',
        )
        p99 = _query_prometheus(
            base_url,
            f'histogram_quantile(0.99, sum(rate(traefik_service_request_duration_seconds_bucket{{service=~"{svc_re}"}}[5m])) by (le))',
        )

        return {
            "status": "available",
            "service": service,
            "namespace": namespace,
            "requestRate": float(req_rate) if req_rate is not None else 0.0,
            "errorRate": round(error_rate, 3),
            "latency": {
                "p50": round(float(p50) * 1000, 3) if p50 is not None else 0.0,
                "p95": round(float(p95) * 1000, 3) if p95 is not None else 0.0,
                "p99": round(float(p99) * 1000, 3) if p99 is not None else 0.0,
            },
        }

    def register(self, mcp_instance) -> None:
        """Register metrics resources with FastMCP."""

        @mcp_instance.resource("argorollout://metrics/{namespace}/{service}/summary")
        async def metrics_summary(namespace: str, service: str) -> str:
            """Get real Prometheus metrics for a service, or explicit unavailable status (fixes B9 & B12)."""
            try:
                prometheus_url = self._get_prometheus_url()
                if not prometheus_url:
                    return json.dumps(
                        {
                            "status": "unavailable",
                            "service": service,
                            "namespace": namespace,
                            "error": "PROMETHEUS_URL is not configured. Configure --prometheus-url or PROMETHEUS_URL.",
                        },
                        indent=2,
                    )

                real_data = await asyncio.to_thread(
                    self._fetch_metrics_from_prometheus,
                    prometheus_url,
                    service,
                    namespace,
                )
                if real_data is not None:
                    return json.dumps(real_data, indent=2)

                return json.dumps(
                    {
                        "status": "unavailable",
                        "service": service,
                        "namespace": namespace,
                        "url": prometheus_url,
                        "error": f"Prometheus at '{prometheus_url}' is unreachable or returned no metrics.",
                    },
                    indent=2,
                )
            except Exception as e:
                logger.error(f"Error getting metrics summary: {e}")
                return json.dumps(
                    {
                        "status": "unavailable",
                        "service": service,
                        "namespace": namespace,
                        "error": str(e),
                    },
                    indent=2,
                )

        @mcp_instance.resource("argorollout://metrics/prometheus/status")
        async def prometheus_status() -> str:
            """Get Prometheus connectivity status."""
            try:
                prometheus_url = self._get_prometheus_url()
                if not prometheus_url:
                    return json.dumps(
                        {
                            "configured": False,
                            "url": None,
                            "status": "unavailable",
                            "message": "PROMETHEUS_URL not set. Set PROMETHEUS_URL env var or --prometheus-url.",
                        },
                        indent=2,
                    )

                reachable = await asyncio.to_thread(_probe_prometheus, prometheus_url)
                if reachable:
                    return json.dumps(
                        {
                            "configured": True,
                            "url": prometheus_url,
                            "status": "available",
                            "message": "Prometheus reachable and responding",
                        },
                        indent=2,
                    )
                return json.dumps(
                    {
                        "configured": True,
                        "url": prometheus_url,
                        "status": "unavailable",
                        "message": "Prometheus URL configured but probe failed (connection refused or timeout)",
                    },
                    indent=2,
                )
            except Exception as e:
                logger.error(f"Error checking Prometheus status: {e}")
                return json.dumps(
                    {
                        "error": str(e),
                        "configured": bool(self._get_prometheus_url()),
                        "status": "error",
                    },
                    indent=2,
                )
