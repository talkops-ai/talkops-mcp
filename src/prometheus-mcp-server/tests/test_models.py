"""Tests for Pydantic data models."""

import pytest

from prometheus_mcp_server.models import (
    BackendCapabilities,
    BackendInfo,
    BackendsSummary,
    CardinalitySummary,
    DownsamplingMetadata,
    ExporterInfo,
    FailedTarget,
    InstantQueryResult,
    InstantSample,
    InstrumentationStrategy,
    LabelTopologyResult,
    MetricCatalog,
    MetricMetadata,
    RangeQueryResult,
    RangeSeries,
    RuntimeConfig,
    ServiceInfo,
    TargetInfo,
    ValidatePromQLResult,
)


class TestBackendModels:
    def test_backend_info_defaults(self):
        info = BackendInfo(id="test", base_url="http://localhost:9090")
        assert info.type == "prometheus"
        assert info.health == "unknown"
        assert info.labels == {}

    def test_backend_capabilities(self):
        caps = BackendCapabilities(
            backend=BackendInfo(id="test", base_url="http://localhost:9090", health="healthy"),
            runtimeinfo={"version": "2.48.0"},
        )
        assert caps.backend.health == "healthy"
        assert caps.runtimeinfo["version"] == "2.48.0"

    def test_backends_summary(self):
        summary = BackendsSummary(backends=[
            BackendInfo(id="a", base_url="http://a:9090"),
            BackendInfo(id="b", base_url="http://b:9090"),
        ])
        assert len(summary.backends) == 2


class TestQueryModels:
    def test_instant_sample(self):
        sample = InstantSample(metric={"job": "test"}, value=(1700000000, "42"))
        assert sample.value[1] == "42"

    def test_instant_query_result(self):
        result = InstantQueryResult(
            resultType="vector",
            result=[InstantSample(metric={"job": "test"}, value=(1.0, "1"))],
            eval_time_seconds=0.05,
            sample_count=1,
        )
        assert result.sample_count == 1

    def test_range_series(self):
        series = RangeSeries(
            metric={"job": "test"},
            values=[(1.0, "1"), (2.0, "2")],
        )
        assert len(series.values) == 2

    def test_validate_result_valid(self):
        result = ValidatePromQLResult(valid=True)
        assert result.errors == []

    def test_validate_result_invalid(self):
        result = ValidatePromQLResult(valid=False, errors=["Parse error at position 5"])
        assert not result.valid
        assert len(result.errors) == 1

    def test_label_topology(self):
        topo = LabelTopologyResult(
            metric_name="up",
            label_names=["job", "instance"],
            label_values={"job": ["prometheus"]},
        )
        assert topo.metric_name == "up"


class TestTargetModels:
    def test_target_info(self):
        target = TargetInfo(job="node-exporter", instance="host:9100", health="up")
        assert target.health == "up"

    def test_service_info(self):
        svc = ServiceInfo(
            service_id="default/prometheus",
            backend_id="default",
            job="prometheus",
            targets_up=3,
            targets_total=3,
        )
        assert svc.targets_up == 3

    def test_failed_target(self):
        ft = FailedTarget(
            backend_id="default",
            job="myapp",
            instance="pod1:8080",
            last_scrape_error="connection refused",
        )
        assert ft.health == "down"


class TestMetadataModels:
    def test_metric_metadata(self):
        meta = MetricMetadata(name="up", type="gauge", help="Target is up")
        assert meta.type == "gauge"

    def test_metric_catalog(self):
        catalog = MetricCatalog(
            metrics=[MetricMetadata(name="up", type="gauge")],
            total_count=1,
        )
        assert catalog.total_count == 1

    def test_runtime_config(self):
        rc = RuntimeConfig(global_config={"scrape_interval": "30s"})
        assert rc.global_config["scrape_interval"] == "30s"


class TestOnboardingModels:
    def test_instrumentation_strategy(self):
        strategy = InstrumentationStrategy(
            strategy="direct_instrumentation",
            rationale="Use client library",
            recommended_client_library="prometheus_client",
        )
        assert strategy.strategy == "direct_instrumentation"


class TestExporterModels:
    def test_exporter_info(self):
        info = ExporterInfo(
            type="node_exporter",
            description="Linux host metrics",
            supported_environments=["kubernetes", "vm"],
            default_scope="daemonset",
        )
        assert info.default_ports.get("metrics", 9100) == 9100
