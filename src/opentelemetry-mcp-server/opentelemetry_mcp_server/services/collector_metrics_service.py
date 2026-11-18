"""Collector internal metrics service.

Fetches and parses the OTel Collector's internal Prometheus metrics
endpoint (``/metrics`` on port 8888) to verify pipeline health:
exporter success/failure, enqueue failures, receiver acceptance/refusal,
processor drops (including incoming/outgoing item deltas), memory usage,
and queue saturation.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from opentelemetry_mcp_server.models.findings import Finding, FindingCode

logger = logging.getLogger(__name__)

_METRIC_LINE_RE = re.compile(
    r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)'
    r'(?:\{(?P<labels>[^}]*)\})?\s+'
    r'(?P<value>[^\s]+)'
)

_LABEL_RE = re.compile(
    r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<val>[^"]*)"'
)

# Metrics we care about for pipeline health (both legacy and modern >= v0.123 names)
_PIPELINE_METRICS = frozenset({
    # Exporter metrics
    "otelcol_exporter_sent_spans",
    "otelcol_exporter_sent_metric_points",
    "otelcol_exporter_sent_log_records",
    "otelcol_exporter_send_failed_spans",
    "otelcol_exporter_send_failed_metric_points",
    "otelcol_exporter_send_failed_log_records",
    "otelcol_exporter_enqueue_failed_spans",
    "otelcol_exporter_enqueue_failed_metric_points",
    "otelcol_exporter_enqueue_failed_log_records",
    "otelcol_exporter_queue_size",
    "otelcol_exporter_queue_capacity",
    # Receiver metrics
    "otelcol_receiver_accepted_spans",
    "otelcol_receiver_accepted_metric_points",
    "otelcol_receiver_accepted_log_records",
    "otelcol_receiver_refused_spans",
    "otelcol_receiver_refused_metric_points",
    "otelcol_receiver_refused_log_records",
    # Processor metrics (legacy + modern incoming/outgoing)
    "otelcol_processor_dropped_spans",
    "otelcol_processor_dropped_metric_points",
    "otelcol_processor_dropped_log_records",
    "otelcol_processor_refused_spans",
    "otelcol_processor_refused_metric_points",
    "otelcol_processor_refused_log_records",
    "otelcol_processor_incoming_items",
    "otelcol_processor_outgoing_items",
    # Memory metrics
    "otelcol_process_memory_rss",
    "otelcol_process_Memory_rss_bytes",
    "process_resident_memory_bytes",
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
    process_memory_rss_bytes: Optional[float] = None
    findings: List[Finding] = field(default_factory=list)
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
            "process_memory_rss_bytes": self.process_memory_rss_bytes,
            "findings": [f.model_dump() for f in self.findings],
            "warnings": self.warnings,
        }


def parse_prometheus_text(text: str) -> List[MetricSample]:
    """Parse Prometheus text exposition format into MetricSample objects."""
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
        if (
            name not in _PIPELINE_METRICS
            and base_name not in _PIPELINE_METRICS
            and not base_name.startswith("otelcol_process_memory_rss")
        ):
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
    """Build a pipeline health report from parsed metric samples."""
    report = PipelineHealthReport(
        collector=f"{namespace}/{collector_name}",
        namespace=namespace,
        metrics_endpoint=metrics_endpoint,
    )

    total_accepted = 0.0

    for s in samples:
        base_name = s.name[:-6] if s.name.endswith("_total") else s.name

        # Memory metrics
        if base_name.startswith("otelcol_process_memory_rss") or base_name == "process_resident_memory_bytes":
            report.process_memory_rss_bytes = s.value
            continue

        # Exporter metrics
        if base_name.startswith("otelcol_exporter_"):
            exporter = s.labels.get("exporter", "unknown")
            if exporter not in report.exporters:
                report.exporters[exporter] = {
                    "sent": {},
                    "failed": {},
                    "enqueue_failed": {},
                }

            if "enqueue_failed" in base_name:
                signal = _extract_signal(base_name, "enqueue_failed")
                report.exporters[exporter]["enqueue_failed"][signal] = s.value
                if s.value > 0:
                    report.healthy = False
                    msg = (
                        f"Exporter '{exporter}' failed to enqueue {int(s.value)} {signal} "
                        "due to a full sending_queue."
                    )
                    report.warnings.append(f"⚠️ {msg}")
                    report.findings.append(
                        Finding.create(
                            FindingCode.RT_ENQUEUE_FAILED,
                            msg,
                            component=f"exporters.{exporter}",
                            evidence={"exporter": exporter, "signal": signal, "enqueue_failed": s.value},
                            next_tool_hint="Increase sending_queue.queue_size or num_consumers via otel_patch_collector.",
                        )
                    )

            elif "send_failed" in base_name:
                signal = _extract_signal(base_name, "send_failed")
                report.exporters[exporter]["failed"][signal] = s.value
                if s.value > 0:
                    report.healthy = False
                    msg = (
                        f"Exporter '{exporter}' has {int(s.value)} failed {signal} sends."
                    )
                    report.warnings.append(
                        f"⚠️ {msg} Check network connectivity and backend health."
                    )
                    report.findings.append(
                        Finding.create(
                            FindingCode.RT_EXPORTER_SEND_FAILED,
                            msg,
                            component=f"exporters.{exporter}",
                            evidence={"exporter": exporter, "signal": signal, "send_failed": s.value},
                            next_tool_hint="Inspect collector pod logs in otel_diagnose_collector for 401/403/TLS/DNS errors.",
                        )
                    )

            elif "sent" in base_name:
                signal = _extract_signal(base_name, "sent")
                report.exporters[exporter]["sent"][signal] = s.value

            elif "queue_size" in base_name:
                if exporter not in report.queue_health:
                    report.queue_health[exporter] = {}
                report.queue_health[exporter]["queue_size"] = s.value

            elif "queue_capacity" in base_name:
                if exporter not in report.queue_health:
                    report.queue_health[exporter] = {}
                report.queue_health[exporter]["queue_capacity"] = s.value

        # Receiver metrics
        elif base_name.startswith("otelcol_receiver_"):
            receiver = s.labels.get("receiver", "unknown")
            transport = s.labels.get("transport", "")
            key = f"{receiver}/{transport}" if transport else receiver
            if key not in report.receivers:
                report.receivers[key] = {
                    "accepted": {},
                    "refused": {},
                }

            if "accepted" in base_name:
                signal = _extract_signal(base_name, "accepted")
                report.receivers[key]["accepted"][signal] = s.value
                total_accepted += s.value

            elif "refused" in base_name:
                signal = _extract_signal(base_name, "refused")
                report.receivers[key]["refused"][signal] = s.value
                if s.value > 0:
                    report.healthy = False
                    msg = f"Receiver '{key}' refused {int(s.value)} {signal}."
                    report.warnings.append(
                        f"⚠️ {msg} This may indicate memory_limiter backpressure or invalid payloads."
                    )
                    report.findings.append(
                        Finding.create(
                            FindingCode.RT_RECEIVER_REFUSED,
                            msg,
                            component=f"receivers.{key}",
                            evidence={"receiver": key, "signal": signal, "refused": s.value},
                        )
                    )

        # Processor metrics
        elif base_name.startswith("otelcol_processor_"):
            processor = s.labels.get("processor", "unknown")
            if processor not in report.processors:
                report.processors[processor] = {
                    "dropped": {},
                    "refused": {},
                    "incoming": {},
                    "outgoing": {},
                }

            if "dropped" in base_name:
                signal = _extract_signal(base_name, "dropped")
                report.processors[processor]["dropped"][signal] = s.value
                if s.value > 0:
                    msg = f"Processor '{processor}' dropped {int(s.value)} {signal}."
                    report.warnings.append(f"⚠️ {msg}")
                    report.findings.append(
                        Finding.create(
                            FindingCode.RT_PROCESSOR_DROPPED,
                            msg,
                            component=f"processors.{processor}",
                            evidence={"processor": processor, "signal": signal, "dropped": s.value},
                        )
                    )
            elif "refused" in base_name:
                signal = _extract_signal(base_name, "refused")
                report.processors[processor]["refused"][signal] = s.value
                if s.value > 0:
                    report.healthy = False
                    msg = f"Processor '{processor}' refused {int(s.value)} {signal} (memory_limiter shedding load)."
                    report.warnings.append(f"⚠️ {msg}")
                    report.findings.append(
                        Finding.create(
                            FindingCode.RT_RECEIVER_REFUSED,
                            msg,
                            component=f"processors.{processor}",
                            evidence={"processor": processor, "signal": signal, "refused": s.value},
                            next_tool_hint="Increase collector memory limits or tune memory_limiter via otel_patch_collector.",
                        )
                    )
            elif base_name == "otelcol_processor_incoming_items":
                sig = s.labels.get("otel.signal", "items")
                report.processors[processor]["incoming"][sig] = s.value
            elif base_name == "otelcol_processor_outgoing_items":
                sig = s.labels.get("otel.signal", "items")
                report.processors[processor]["outgoing"][sig] = s.value

    # Check incoming > outgoing deltas on processors
    for processor, pdata in report.processors.items():
        inc_map = pdata.get("incoming") or {}
        out_map = pdata.get("outgoing") or {}
        for sig, inc_val in inc_map.items():
            if sig in out_map and inc_val > out_map[sig]:
                delta = inc_val - out_map[sig]
                msg = (
                    f"Processor '{processor}' received {int(inc_val)} '{sig}' items "
                    f"but emitted {int(out_map[sig])} ({int(delta)} filtered/dropped)."
                )
                report.warnings.append(f"⚠️ {msg}")
                report.findings.append(
                    Finding.create(
                        FindingCode.RT_PROCESSOR_DROPPED,
                        msg,
                        component=f"processors.{processor}",
                        evidence={
                            "processor": processor,
                            "signal": sig,
                            "incoming": inc_val,
                            "outgoing": out_map[sig],
                            "dropped_delta": delta,
                        },
                    )
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
                msg = (
                    f"Exporter '{exporter}' queue is {q['utilization_pct']}% full "
                    f"({int(size)}/{int(capacity)})."
                )
                report.warnings.append(
                    f"⚠️ {msg} Risk of data loss due to backpressure."
                )
                report.findings.append(
                    Finding.create(
                        FindingCode.RT_QUEUE_SATURATED,
                        msg,
                        component=f"exporters.{exporter}",
                        evidence={
                            "exporter": exporter,
                            "queue_size": size,
                            "queue_capacity": capacity,
                            "utilization_pct": q["utilization_pct"],
                        },
                    )
                )

    if report.receivers and total_accepted == 0:
        report.findings.append(
            Finding.create(
                FindingCode.RT_NO_DATA_RECEIVED,
                "Collector receivers are active but have accepted 0 telemetry items across all signals.",
                component="receivers",
                evidence={"receivers": list(report.receivers.keys()), "total_accepted": 0},
                next_tool_hint="Verify workload instrumentation via otel_verify_instrumentation.",
            )
        )

    if report.healthy and not report.findings:
        report.findings.append(
            Finding.create(
                FindingCode.RT_HEALTHY,
                "Collector internal pipeline metrics are healthy with zero send or enqueue failures.",
                component=f"{namespace}/{collector_name}",
            )
        )

    return report


def _extract_signal(metric_name: str, keyword: str) -> str:
    """Extract the signal type from a metric name."""
    parts = metric_name.split(f"_{keyword}_")
    if len(parts) > 1:
        signal = parts[-1]
        if signal.endswith("_total"):
            return signal[:-6]
        return signal
    return "unknown"


class CollectorMetricsService:
    """Service for fetching and analyzing OTel Collector internal metrics."""

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
        """Fetch and analyze collector pipeline health via internal metrics."""
        from opentelemetry_mcp_server.exceptions import OtelOperationError

        candidate_endpoints = [
            f"http://{collector_name}-collector-monitoring.{namespace}.svc.cluster.local:{metrics_port}{self.METRICS_PATH}",
            f"http://{collector_name}-collector.{namespace}.svc.cluster.local:{metrics_port}{self.METRICS_PATH}",
            f"http://{collector_name}.{namespace}.svc.cluster.local:{metrics_port}{self.METRICS_PATH}",
        ]

        metrics_text = None
        metrics_endpoint = None

        for endpoint in candidate_endpoints:
            try:
                metrics_text = await self._fetch_metrics_via_pod(
                    namespace,
                    collector_name,
                    endpoint,
                    metrics_port=metrics_port,
                )
                if metrics_text and "otelcol_" in metrics_text:
                    metrics_endpoint = endpoint
                    break
            except Exception:
                continue

        if not metrics_text or not metrics_endpoint:
            raise OtelOperationError(
                f"Cannot fetch internal metrics for collector "
                f"'{namespace}/{collector_name}'. Tried endpoints: "
                f"{candidate_endpoints}. Ensure the collector has "
                "internal telemetry enabled via "
                "service.telemetry.metrics.readers (port 8888)."
            )

        samples = parse_prometheus_text(metrics_text)
        if not samples:
            return PipelineHealthReport(
                collector=f"{namespace}/{collector_name}",
                namespace=namespace,
                metrics_endpoint=metrics_endpoint,
                findings=[
                    Finding.create(
                        FindingCode.RT_METRICS_UNREACHABLE,
                        "No otelcol_* metrics found in response from internal telemetry endpoint.",
                        component=f"{namespace}/{collector_name}",
                    )
                ],
                warnings=[
                    "No otelcol_* metrics found in the response. "
                    "Ensure service.telemetry.metrics.readers is configured on port 8888."
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
        metrics_port: int = DEFAULT_METRICS_PORT,
    ) -> Optional[str]:
        """Fetch metrics via Kubernetes API pod proxy (distroless-safe)."""
        import asyncio

        try:
            crd_selector = None
            custom_api = getattr(
                self._kubernetes_service,
                "_custom_api",
                getattr(self._kubernetes_service, "_custom_objects_api", None),
            )
            if custom_api is not None:
                try:
                    crd = await asyncio.to_thread(
                        custom_api.get_namespaced_custom_object,
                        group="opentelemetry.io",
                        version="v1beta1",
                        namespace=namespace,
                        plural="opentelemetrycollectors",
                        name=collector_name,
                    )
                    crd_selector = (
                        crd.get("status", {}).get("scale", {}).get("selector")
                    )
                except Exception as e:
                    logger.debug(f"Could not fetch CRD scale selector: {e}")

            target_pod = None
            if crd_selector:
                pods = await asyncio.to_thread(
                    self._kubernetes_service._core_v1.list_namespaced_pod,
                    namespace=namespace,
                    label_selector=crd_selector,
                    limit=1,
                )
                if pods.items:
                    target_pod = pods.items[0]

            if not target_pod:
                pods = await asyncio.to_thread(
                    self._kubernetes_service._core_v1.list_namespaced_pod,
                    namespace=namespace,
                    label_selector="app.kubernetes.io/component=opentelemetry-collector",
                )
                for pod in pods.items:
                    labels = pod.metadata.labels or {}
                    instance = labels.get("app.kubernetes.io/instance", "")
                    name_label = labels.get("app.kubernetes.io/name", "")

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
            metrics_path = self.METRICS_PATH.lstrip("/")
            resp = await asyncio.to_thread(
                self._kubernetes_service._core_v1.connect_get_namespaced_pod_proxy_with_path,
                name=f"{pod_name}:{metrics_port}",
                namespace=namespace,
                path=metrics_path,
            )

            return resp.decode("utf-8") if isinstance(resp, bytes) else str(resp)

        except Exception as e:
            logger.debug(f"Failed to fetch metrics via pod proxy: {e}")
            return None
