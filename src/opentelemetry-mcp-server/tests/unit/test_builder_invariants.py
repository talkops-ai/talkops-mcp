"""T-U1: Unit tests for collector_config_builder.py production invariants."""

from __future__ import annotations

from unittest.mock import MagicMock

from opentelemetry_mcp_server.services.collector_config_builder import (
    CollectorConfigBuilder,
)


def _make_builder() -> CollectorConfigBuilder:
    return CollectorConfigBuilder(MagicMock())


def test_classify_exporter_otlp_vs_otlphttp():
    builder = _make_builder()
    # Plain gRPC endpoint -> otlp/traces, otlp (not false-matched on 'http://')
    exp_name, exp_type = builder._classify_exporter("traces", "http://tempo.observability.svc:4317")
    assert exp_name == "otlp/traces"
    assert exp_type == "otlp"

    # Explicit /api/v1/otlp path -> otlphttp
    exp_name_v1, exp_type_v1 = builder._classify_exporter(
        "metrics", "https://mimir.observability.svc/api/v1/otlp"
    )
    assert exp_name_v1 == "otlphttp/metrics"
    assert exp_type_v1 == "otlphttp"


def test_tls_verification_default_on_https_endpoints():
    builder = _make_builder()
    cfg = builder.build_config(
        signals=["traces"],
        exporter_targets={"traces": "https://ingest.vendor.example.com:4317"},
        mode="deployment",
        role="gateway",
    )
    exporters = cfg["exporters"]
    exp = next(iter(exporters.values()))
    assert exp["tls"]["insecure"] is False

    # Cluster-local plaintext http:// -> insecure=True
    cfg_local = builder.build_config(
        signals=["traces"],
        exporter_targets={"traces": "http://tempo.observability.svc.cluster.local:4317"},
        mode="deployment",
        role="gateway",
    )
    exp_local = next(iter(cfg_local["exporters"].values()))
    assert exp_local["tls"]["insecure"] is True


def test_internal_telemetry_uses_v0120_readers_pull_schema():
    builder = _make_builder()
    cfg = builder.build_config(
        signals=["traces", "metrics"],
        exporter_targets={"traces": "tempo:4317", "metrics": "mimir:9009"},
        mode="daemonset",
        role="agent",
    )
    metrics_tel = cfg["service"]["telemetry"]["metrics"]
    assert "address" not in metrics_tel
    readers = metrics_tel["readers"]
    assert isinstance(readers, list) and len(readers) == 1
    prom = readers[0]["pull"]["exporter"]["prometheus"]
    assert prom["host"] == "0.0.0.0"
    assert prom["port"] == 8888


def test_daemonset_k8sattributes_includes_k8s_node_name_filter():
    builder = _make_builder()
    cfg = builder.build_config(
        signals=["traces"],
        exporter_targets={"traces": "tempo:4317"},
        mode="daemonset",
        role="agent",
    )
    k8s_attr = cfg["processors"]["k8sattributes"]
    assert k8s_attr["filter"]["node_from_env_var"] == "K8S_NODE_NAME"


def test_exporters_include_sending_queue_and_retry_on_failure():
    builder = _make_builder()
    cfg = builder.build_config(
        signals=["traces", "metrics"],
        exporter_targets={"traces": "tempo:4317", "metrics": "mimir:9009"},
        mode="deployment",
        role="gateway",
    )
    for exp_name, exp_cfg in cfg["exporters"].items():
        if exp_name.startswith("otlp"):
            assert exp_cfg["sending_queue"]["enabled"] is True
            assert exp_cfg["retry_on_failure"]["enabled"] is True


def test_servicegraph_connector_wires_traces_to_metrics():
    builder = _make_builder()
    cfg = builder.build_config(
        signals=["traces", "metrics"],
        exporter_targets={"traces": "tempo:4317", "metrics": "mimir:9009"},
        mode="deployment",
        role="gateway",
        enable_servicegraph=True,
    )
    assert "servicegraph" in cfg["connectors"]
    assert "servicegraph" in cfg["service"]["pipelines"]["traces"]["exporters"]
    assert "servicegraph" in cfg["service"]["pipelines"]["metrics"]["receivers"]
