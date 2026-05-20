"""Metrics summary resources.

Provides key performance metrics from Prometheus (when available).
"""

import json
import logging
from typing import Optional, Dict, Any
from urllib.parse import urljoin, quote

import requests

from argo_rollout_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


def _query_prometheus(base_url: str, query: str, timeout: float = 5.0) -> Optional[float]:
    """Execute a PromQL instant query and return the first scalar value.

    Returns None if the query fails or returns no data.
    """
    try:
        url = urljoin(base_url.rstrip("/") + "/", f"api/v1/query?query={quote(query)}")
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            return None
        result = data.get("data", {}).get("result", [])
        if not result:
            return None
        # Instant query returns [[timestamp, value]] for scalar
        val = result[0].get("value")
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
    """Metrics summary resources.

    Provides key performance metrics from Prometheus when configured. When Prometheus
    is unavailable or not yet integrated, returns mock data with placeholder=true —
    LLMs should not rely on these values for decision-making in that case.
    Update frequency: Every 10 seconds.
    """

    def _get_prometheus_url(self) -> Optional[str]:
        """Get Prometheus URL from config."""
        if not self.config:
            return None
        return getattr(self.config, "prometheus_url", None)

    def _fetch_metrics_from_prometheus(
        self, base_url: str, service: str, namespace: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch real metrics from Prometheus. Returns None on failure."""
        # Service label in Traefik metrics may match K8s service name (e.g. my-app-stable, my-app-canary)
        # Escape for PromQL regex: backslash and double-quote
        svc_escaped = service.replace("\\", "\\\\").replace('"', '\\"')
        svc_re = f'.*{svc_escaped}.*'

        # Request rate: sum of all requests per second
        req_rate_query = f'sum(rate(traefik_service_requests_total{{service=~"{svc_re}"}}[5m]))'
        req_rate = _query_prometheus(base_url, req_rate_query)

        # 5xx rate for error rate
        err_count_query = f'sum(rate(traefik_service_requests_total{{code=~"5..",service=~"{svc_re}"}}[5m]))'
        err_count = _query_prometheus(base_url, err_count_query)
        total_count_query = f'sum(rate(traefik_service_requests_total{{service=~"{svc_re}"}}[5m]))'
        total_count = _query_prometheus(base_url, total_count_query)

        error_rate = 0.0
        if total_count is not None and total_count > 0 and err_count is not None:
            error_rate = (err_count / total_count) * 100.0

        # Latency percentiles from histogram (Traefik reports in seconds)
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

        # If we got at least request rate or error rate, consider it a success
        if req_rate is not None or total_count is not None:
            return {
                "service": service,
                "namespace": namespace,
                "requestRate": float(req_rate) if req_rate is not None else 0.0,
                "errorRate": error_rate,
                "latency": {
                    "p50": float(p50) * 1000 if p50 is not None else 0.0,
                    "p95": float(p95) * 1000 if p95 is not None else 0.0,
                    "p99": float(p99) * 1000 if p99 is not None else 0.0,
                },
                "resources": {"cpu": 0.0, "memory": 0},
                "placeholder": False,
                "note": "Real metrics from Prometheus (Traefik)",
            }
        return None

    def register(self, mcp_instance) -> None:
        """Register metrics resources with FastMCP.

        Args:
            mcp_instance: FastMCP server instance
        """

        @mcp_instance.resource("argorollout://metrics/{namespace}/{service}/summary")
        async def metrics_summary(namespace: str, service: str) -> str:
            """Get metrics summary for a service.

            Returns real Prometheus-sourced metrics when configured and reachable;
            otherwise returns mock data with placeholder=true. Do not rely on values
            for decision-making when placeholder=true.

            Args:
                namespace: Kubernetes namespace
                service: Service name

            Returns:
                JSON with requestRate, errorRate, latency (p50/p95/p99), resources.
                Includes placeholder: true when using mock data.
            """
            try:
                prometheus_url = self._get_prometheus_url()
                if prometheus_url:
                    real_data = self._fetch_metrics_from_prometheus(
                        prometheus_url, service, namespace
                    )
                    if real_data is not None:
                        logger.info(
                            f"Metrics for {service} in {namespace}: "
                            f"requestRate={real_data.get('requestRate')}, "
                            f"errorRate={real_data.get('errorRate')}%"
                        )
                        return json.dumps(real_data, indent=2)

                # Fallback: placeholder data
                resource_data = {
                    "service": service,
                    "namespace": namespace,
                    "requestRate": 0.0,
                    "errorRate": 0.0,
                    "latency": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
                    "resources": {"cpu": 0.0, "memory": 0},
                    "placeholder": True,
                    "note": "Prometheus unreachable or not configured; using placeholder. Do not use for decision-making.",
                }
                logger.info(
                    f"Metrics requested for {service} in {namespace} (Prometheus unreachable or not configured)"
                )
                return json.dumps(resource_data, indent=2)

            except Exception as e:
                logger.error(f"Error getting metrics summary: {e}")
                return json.dumps(
                    {"error": str(e), "placeholder": True, "service": service, "namespace": namespace},
                    indent=2,
                )

        @mcp_instance.resource("argorollout://metrics/prometheus/status")
        async def prometheus_status() -> str:
            """Get Prometheus integration status.

            Probes Prometheus to report available/unavailable when configured.
            Returns placeholder: true only when Prometheus is not configured.

            Returns:
                JSON with configured, url, status, message. status is 'available'
                when probe succeeds, 'unavailable' otherwise.
            """
            try:
                prometheus_url = self._get_prometheus_url()
                if not prometheus_url:
                    resource_data = {
                        "configured": False,
                        "url": "Not configured",
                        "status": "unavailable",
                        "message": "PROMETHEUS_URL not set. Set PROMETHEUS_URL env var (e.g. http://prometheus:9090).",
                        "placeholder": True,
                    }
                    return json.dumps(resource_data, indent=2)

                # Probe Prometheus
                if _probe_prometheus(prometheus_url):
                    resource_data = {
                        "configured": True,
                        "url": prometheus_url,
                        "status": "available",
                        "message": "Prometheus reachable and responding",
                        "placeholder": False,
                    }
                else:
                    resource_data = {
                        "configured": True,
                        "url": prometheus_url,
                        "status": "unavailable",
                        "message": "Prometheus URL configured but probe failed (connection refused or timeout)",
                        "placeholder": False,
                    }
                return json.dumps(resource_data, indent=2)

            except Exception as e:
                logger.error(f"Error checking Prometheus status: {e}")
                return json.dumps(
                    {
                        "error": str(e),
                        "configured": bool(self._get_prometheus_url()),
                        "status": "error",
                        "placeholder": False,
                    },
                    indent=2,
                )
