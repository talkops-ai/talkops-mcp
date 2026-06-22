"""Collector internal metrics service.

Fetches and parses the OTel Collector's internal Prometheus metrics
endpoint (``/metrics`` on port 8888) to verify pipeline health:
exporter success/failure, receiver acceptance, and queue saturation.

This approach is **backend-agnostic** — it works regardless of whether
the collector exports to Jaeger, Tempo, Prometheus, Loki, or any other
destination.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Prometheus text format parser (minimal)
# ──────────────────────────────────────────────

_METRIC_LINE_RE = re.compile(
    r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)'
    r'(?:\{(?P<labels>[^}]*)\})?\s+'
    r'(?P<value>[^\s]+)'
)

_LABEL_RE = re.compile(
    r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<val>[^"]*)"'
)

# Metrics we care about for pipeline health
_PIPELINE_METRICS = frozenset({
    # Exporter metrics
    "otelcol_exporter_sent_spans",
    "otelcol_exporter_sent_metric_points",
    "otelcol_exporter_sent_log_records",
    "otelcol_exporter_send_failed_spans",
    "otelcol_exporter_send_failed_metric_points",
    "otelcol_exporter_send_failed_log_records",
    "otelcol_exporter_queue_size",
    "otelcol_exporter_queue_capacity",
    # Receiver metrics
    "otelcol_receiver_accepted_spans",
    "otelcol_receiver_accepted_metric_points",
    "otelcol_receiver_accepted_log_records",
    "otelcol_receiver_refused_spans",
    "otelcol_receiver_refused_metric_points",
    "otelcol_receiver_refused_log_records",
    # Processor metrics
    "otelcol_processor_dropped_spans",
    "otelcol_processor_dropped_metric_points",
    "otelcol_processor_dropped_log_records",
})


@dataclass
class MetricSample:
    """A single metric sample with labels and value."""

    name: str
    labels: Dict[str, str]
    value: float


@dataclass
class PipelineHealthReport:
    """Aggregated pipeline health from collector internal metrics."""

    collector: str
    namespace: str
    metrics_endpoint: str
    exporters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    receivers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    processors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    queue_health: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    healthy: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return {
            "collector": self.collector,
            "namespace": self.namespace,
            "metrics_endpoint": self.metrics_endpoint,
            "healthy": self.healthy,
            "exporters": self.exporters,
            "receivers": self.receivers,
            "processors": self.processors,
            "queue_health": self.queue_health,
            "warnings": self.warnings,
        }


def parse_prometheus_text(text: str) -> List[MetricSample]:
    """Parse Prometheus text exposition format into MetricSample objects.

    Only extracts metrics whose names match ``_PIPELINE_METRICS``.
    Lines starting with ``#`` are skipped (HELP/TYPE comments).

    Args:
        text: Raw Prometheus text format response body.

    Returns:
        List of MetricSample for pipeline-relevant metrics.
    """
    samples: List[MetricSample] = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = _METRIC_LINE_RE.match(line)
        if not match:
            continue

        name = match.group("name")
        base_name = name[:-6] if name.endswith("_total") else name
        if name not in _PIPELINE_METRICS and base_name not in _PIPELINE_METRICS:
            continue

        labels_str = match.group("labels") or ""
        labels: Dict[str, str] = {}
        for lm in _LABEL_RE.finditer(labels_str):
            labels[lm.group("key")] = lm.group("val")

        try:
            value = float(match.group("value"))
        except ValueError:
            continue

        samples.append(MetricSample(name=name, labels=labels, value=value))

    return samples


def build_health_report(
    samples: List[MetricSample],
    collector_name: str,
    namespace: str,
    metrics_endpoint: str,
) -> PipelineHealthReport:
    """Build a pipeline health report from parsed metric samples.

    Groups metrics by exporter/receiver/processor and checks for
    failure conditions (failed sends, queue saturation, dropped data).

    Args:
        samples: Parsed MetricSample objects.
        collector_name: Name of the collector.
        namespace: Collector namespace.
        metrics_endpoint: The URL that was scraped.

    Returns:
        Aggregated PipelineHealthReport.
    """
    report = PipelineHealthReport(
        collector=f"{namespace}/{collector_name}",
        namespace=namespace,
        metrics_endpoint=metrics_endpoint,
    )

    for s in samples:
        # Exporter metrics
        if s.name.startswith("otelcol_exporter_"):
            exporter = s.labels.get("exporter", "unknown")
            if exporter not in report.exporters:
                report.exporters[exporter] = {
                    "sent": {},
                    "failed": {},
                }

            if "sent" in s.name:
                signal = _extract_signal(s.name, "sent")
                report.exporters[exporter]["sent"][signal] = s.value

            elif "failed" in s.name:
                signal = _extract_signal(s.name, "send_failed")
                report.exporters[exporter]["failed"][signal] = s.value
                if s.value > 0:
                    report.healthy = False
                    report.warnings.append(
                        f"⚠️ Exporter '{exporter}' has {int(s.value)} "
                        f"failed {signal} sends. Check network connectivity "
                        "and backend health."
                    )

            elif "queue_size" in s.name:
                if exporter not in report.queue_health:
                    report.queue_health[exporter] = {}
                report.queue_health[exporter]["queue_size"] = s.value

            elif "queue_capacity" in s.name:
                if exporter not in report.queue_health:
                    report.queue_health[exporter] = {}
                report.queue_health[exporter]["queue_capacity"] = s.value

        # Receiver metrics
        elif s.name.startswith("otelcol_receiver_"):
            receiver = s.labels.get("receiver", "unknown")
            transport = s.labels.get("transport", "")
            key = f"{receiver}/{transport}" if transport else receiver
            if key not in report.receivers:
                report.receivers[key] = {
                    "accepted": {},
                    "refused": {},
                }

            if "accepted" in s.name:
                signal = _extract_signal(s.name, "accepted")
                report.receivers[key]["accepted"][signal] = s.value

            elif "refused" in s.name:
                signal = _extract_signal(s.name, "refused")
                report.receivers[key]["refused"][signal] = s.value
                if s.value > 0:
                    report.warnings.append(
                        f"⚠️ Receiver '{key}' has refused {int(s.value)} "
                        f"{signal}. This may indicate backpressure or "
                        "misconfigured sender."
                    )

        # Processor metrics
        elif s.name.startswith("otelcol_processor_"):
            processor = s.labels.get("processor", "unknown")
            if processor not in report.processors:
                report.processors[processor] = {"dropped": {}}

            if "dropped" in s.name:
                signal = _extract_signal(s.name, "dropped")
                report.processors[processor]["dropped"][signal] = s.value
                if s.value > 0:
                    report.warnings.append(
                        f"⚠️ Processor '{processor}' has dropped "
                        f"{int(s.value)} {signal}."
                    )

    # Check queue saturation
    for exporter, q in report.queue_health.items():
        size = q.get("queue_size", 0)
        capacity = q.get("queue_capacity", 0)
        if capacity > 0:
            utilization = size / capacity
            q["utilization_pct"] = round(utilization * 100, 1)
            if utilization > 0.8:
                report.healthy = False
                report.warnings.append(
                    f"⚠️ Exporter '{exporter}' queue is {q['utilization_pct']}% "
                    f"full ({int(size)}/{int(capacity)}). Risk of data loss "
                    "due to backpressure."
                )

    return report


def _extract_signal(metric_name: str, keyword: str) -> str:
    """Extract the signal type from a metric name.

    E.g., 'otelcol_exporter_sent_spans' → 'spans'
          'otelcol_receiver_accepted_metric_points' → 'metric_points'
    """
    parts = metric_name.split(f"_{keyword}_")
    if len(parts) > 1:
        signal = parts[-1]
        if signal.endswith("_total"):
            return signal[:-6]
        return signal
    return "unknown"


class CollectorMetricsService:
    """Service for fetching and analyzing OTel Collector internal metrics.

    Uses the Kubernetes CoreV1Api to read the collector's internal
    metrics endpoint via port-forward or Service DNS resolution.
    """

    # The OTel Collector exposes internal metrics on port 8888 by default
    DEFAULT_METRICS_PORT = 8888
    METRICS_PATH = "/metrics"

    def __init__(self, kubernetes_service: Any) -> None:
        self._kubernetes_service = kubernetes_service

    async def fetch_pipeline_health(
        self,
        namespace: str,
        collector_name: str,
        metrics_port: int = DEFAULT_METRICS_PORT,
    ) -> PipelineHealthReport:
        """Fetch and analyze collector pipeline health via internal metrics.

        Constructs a K8s Service URL for the collector and reads its
        Prometheus metrics endpoint. Falls back to pod-level access
        if the service is not found.

        Args:
            namespace: Collector namespace.
            collector_name: Collector CRD name.
            metrics_port: Internal metrics port (default 8888).

        Returns:
            PipelineHealthReport with per-exporter/receiver health.

        Raises:
            OtelOperationError: If metrics cannot be fetched.
        """
        from opentelemetry_mcp_server.exceptions import OtelOperationError

        # Build the internal Service DNS name
        # The OTel Operator creates services with pattern: {name}-collector-monitoring
        # or {name}-collector (we try both patterns)
        candidate_endpoints = [
            f"http://{collector_name}-collector-monitoring.{namespace}.svc.cluster.local:{metrics_port}{self.METRICS_PATH}",
            f"http://{collector_name}-collector.{namespace}.svc.cluster.local:{metrics_port}{self.METRICS_PATH}",
            f"http://{collector_name}.{namespace}.svc.cluster.local:{metrics_port}{self.METRICS_PATH}",
        ]

        # Try to fetch metrics by exec'ing curl inside a collector pod
        metrics_text = None
        metrics_endpoint = None

        for endpoint in candidate_endpoints:
            try:
                metrics_text = await self._fetch_metrics_via_pod(
                    namespace, collector_name, endpoint
                )
                if metrics_text and "otelcol_" in metrics_text:
                    metrics_endpoint = endpoint
                    break
            except Exception:
                continue

        if not metrics_text or not metrics_endpoint:
            # Construct a helpful error showing what we tried
            raise OtelOperationError(
                f"Cannot fetch internal metrics for collector "
                f"'{namespace}/{collector_name}'. Tried endpoints: "
                f"{candidate_endpoints}. Ensure the collector has "
                "internal telemetry enabled at "
                "service.telemetry.metrics.address."
            )

        samples = parse_prometheus_text(metrics_text)
        if not samples:
            return PipelineHealthReport(
                collector=f"{namespace}/{collector_name}",
                namespace=namespace,
                metrics_endpoint=metrics_endpoint,
                warnings=[
                    "No otelcol_* metrics found in the response. "
                    "The collector may not have internal telemetry enabled. "
                    "Set service.telemetry.metrics.address in the config."
                ],
            )

        return build_health_report(
            samples, collector_name, namespace, metrics_endpoint
        )

    async def _fetch_metrics_via_pod(
        self,
        namespace: str,
        collector_name: str,
        endpoint: str,
    ) -> Optional[str]:
        """Fetch metrics by exec'ing wget inside a collector pod.

        Falls back to reading from within the cluster using the
        Kubernetes API stream exec.

        Args:
            namespace: Pod namespace.
            collector_name: Collector name for pod label selection.
            endpoint: Full URL to fetch.

        Returns:
            Raw metrics text, or None if unavailable.
        """
        import asyncio

        try:
            # Most robust approach: read the exact label selector the Operator uses
            # from the OpenTelemetryCollector CRD status
            crd_selector = None
            try:
                crd = await asyncio.to_thread(
                    self._kubernetes_service._custom_objects_api.get_namespaced_custom_object,
                    group="opentelemetry.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="opentelemetrycollectors",
                    name=collector_name,
                )
                crd_selector = crd.get("status", {}).get("scale", {}).get("selector")
            except Exception as e:
                logger.debug(f"Could not fetch CRD scale selector: {e}")

            target_pod = None
            if crd_selector:
                # Use the exact selector from the CRD
                pods = await asyncio.to_thread(
                    self._kubernetes_service._core_v1.list_namespaced_pod,
                    namespace=namespace,
                    label_selector=crd_selector,
                    limit=1,
                )
                if pods.items:
                    target_pod = pods.items[0]

            # Fallback if CRD status is unavailable or empty
            if not target_pod:
                # Fetch all collector pods in the namespace using a generic label
                pods = await asyncio.to_thread(
                    self._kubernetes_service._core_v1.list_namespaced_pod,
                    namespace=namespace,
                    label_selector="app.kubernetes.io/component=opentelemetry-collector",
                )
                for pod in pods.items:
                    labels = pod.metadata.labels or {}
                    instance = labels.get("app.kubernetes.io/instance", "")
                    name_label = labels.get("app.kubernetes.io/name", "")

                    # Match if instance ends with the collector name (handles both
                    # opentelemetry.io- prefix and namespace. prefix variations)
                    # or if the name label explicitly matches.
                    if (
                        instance.endswith(f"-{collector_name}")
                        or instance.endswith(f".{collector_name}")
                        or instance == collector_name
                        or name_label == f"{collector_name}-collector"
                    ):
                        target_pod = pod
                        break

            if not target_pod:
                return None

            pod_name = target_pod.metadata.name

            # Use the Kubernetes proxy API to securely route the request through the API server
            # This completely avoids the need for utilities like `wget` or `curl` in the pod,
            # making it fully compatible with distroless container images.
            metrics_path = self.METRICS_PATH.lstrip("/")
            resp = await asyncio.to_thread(
                self._kubernetes_service._core_v1.connect_get_namespaced_pod_proxy_with_path,
                name=f"{pod_name}:{self.DEFAULT_METRICS_PORT}",
                namespace=namespace,
                path=metrics_path,
            )

            # The proxy response might be returned as bytes
            return resp.decode("utf-8") if isinstance(resp, bytes) else str(resp)

        except Exception as e:
            logger.debug(
                f"Failed to fetch metrics via pod exec: {e}"
            )
            return None
