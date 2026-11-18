"""T-U5: Unit tests for CollectorMetricsService parsing & RT_* findings (B2 & B5 fixes)."""

from __future__ import annotations

from opentelemetry_mcp_server.models.findings import FindingCode
from opentelemetry_mcp_server.services.collector_metrics_service import (
    build_health_report,
    parse_prometheus_text,
)

SAMPLE_METRICS = """
# HELP otelcol_receiver_accepted_spans Number of spans successfully pushed into the pipeline.
# TYPE otelcol_receiver_accepted_spans counter
otelcol_receiver_accepted_spans{receiver="otlp",service_instance_id="1",transport="grpc"} 1540
otelcol_receiver_refused_spans{receiver="otlp",service_instance_id="1",transport="grpc"} 12
otelcol_processor_refused_spans{processor="memory_limiter"} 5
otelcol_exporter_sent_spans{exporter="otlp/traces"} 1500
otelcol_exporter_send_failed_spans{exporter="otlp/traces"} 20
otelcol_exporter_enqueue_failed_spans{exporter="otlp/traces"} 3
otelcol_exporter_queue_size{exporter="otlp/traces"} 850
otelcol_exporter_queue_capacity{exporter="otlp/traces"} 1000
otelcol_process_memory_rss 480000000
"""


def test_parse_metrics_and_detect_drops_and_saturation():
    samples = parse_prometheus_text(SAMPLE_METRICS)
    assert len(samples) >= 8

    report = build_health_report(
        samples=samples,
        collector_name="otel-agent",
        namespace="default",
        metrics_endpoint="http://otel-agent:8888/metrics",
    )
    summary = report.to_dict()
    assert summary["healthy"] is False
    assert summary["receivers"]["otlp/grpc"]["accepted"]["spans"] == 1540.0
    assert summary["receivers"]["otlp/grpc"]["refused"]["spans"] == 12.0
    assert summary["exporters"]["otlp/traces"]["sent"]["spans"] == 1500.0
    assert summary["exporters"]["otlp/traces"]["failed"]["spans"] == 20.0
    assert summary["exporters"]["otlp/traces"]["enqueue_failed"]["spans"] == 3.0
    assert summary["process_memory_rss_bytes"] == 480000000.0

    codes = {f["code"] for f in summary["findings"]}
    assert FindingCode.RT_EXPORTER_SEND_FAILED.value in codes
    assert FindingCode.RT_ENQUEUE_FAILED.value in codes
    assert FindingCode.RT_RECEIVER_REFUSED.value in codes
    assert FindingCode.RT_QUEUE_SATURATED.value in codes
