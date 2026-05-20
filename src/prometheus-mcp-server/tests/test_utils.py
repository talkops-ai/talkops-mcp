"""Tests for utility modules."""

import pytest
from prometheus_mcp_server.utils.promql_helpers import (
    compute_auto_step,
    downsample_series,
    enforce_counter_rule_sync,
)

from prometheus_mcp_server.utils.exporter_catalog import (
    build_exporter_manifests,
    build_servicemonitor_manifest,
    list_exporters,
    recommend_exporters,
)


class TestPromQLHelpers:
    def test_counter_rule_blocks_counter(self):
        metadata = {"http_requests_total": [{"type": "counter"}]}
        result = enforce_counter_rule_sync(metadata, "http_requests_total", False)
        assert result is not None
        assert "rate()" in result

    def test_counter_rule_allows_gauge(self):
        metadata = {"up": [{"type": "gauge"}]}
        assert enforce_counter_rule_sync(metadata, "up", False) is None

    def test_counter_rule_allows_override(self):
        metadata = {"http_requests_total": [{"type": "counter"}]}
        assert enforce_counter_rule_sync(metadata, "http_requests_total", True) is None

    def test_counter_rule_allows_function_wrapped(self):
        metadata = {"http_requests_total": [{"type": "counter"}]}
        assert enforce_counter_rule_sync(metadata, "rate(http_requests_total[5m])", False) is None

    def test_counter_rule_blocks_sum_of_raw_counter(self):
        """sum(counter) without rate() should be blocked."""
        metadata = {"http_requests_total": [{"type": "counter"}]}
        result = enforce_counter_rule_sync(metadata, "sum(http_requests_total)", False)
        assert result is not None
        assert "rate()" in result

    def test_counter_rule_allows_sum_rate(self):
        """sum(rate(counter[5m])) should pass because rate() wraps the counter."""
        metadata = {"http_requests_total": [{"type": "counter"}]}
        assert enforce_counter_rule_sync(metadata, "sum(rate(http_requests_total[5m]))", False) is None

    def test_counter_rule_allows_increase(self):
        """increase(counter[1h]) should pass."""
        metadata = {"http_requests_total": [{"type": "counter"}]}
        assert enforce_counter_rule_sync(metadata, "increase(http_requests_total[1h])", False) is None

    def test_counter_rule_blocks_counter_with_labels(self):
        """counter{label='x'} without rate() should be blocked."""
        metadata = {"http_requests_total": [{"type": "counter"}]}
        result = enforce_counter_rule_sync(metadata, "http_requests_total{method='GET'}", False)
        assert result is not None

    def test_downsample_no_op(self):
        vals = [(float(i), float(i)) for i in range(10)]
        assert len(downsample_series(vals, 20)) == 10

    def test_downsample_reduces(self):
        vals = [(float(i), float(i)) for i in range(1000)]
        result = downsample_series(vals, 100)
        assert len(result) <= 100

    def test_compute_auto_step_short(self):
        step = compute_auto_step(0, 300, 200)
        assert step == "2s"

    def test_compute_auto_step_long(self):
        step = compute_auto_step(0, 86400, 200)
        assert "m" in step or "s" in step

    def test_compute_auto_step_zero_duration(self):
        assert compute_auto_step(100, 100, 200) == "15s"





class TestExporterCatalog:
    def test_list_exporters(self):
        exporters = list_exporters()
        assert len(exporters) >= 7
        types = [e.type for e in exporters]
        assert "node_exporter" in types
        assert "postgres_exporter" in types

    def test_recommend_postgres(self):
        recs, notes = recommend_exporters("postgres", "kubernetes")
        assert len(recs) >= 1
        assert recs[0].type == "postgres_exporter"

    def test_recommend_unknown_service(self):
        recs, notes = recommend_exporters("unknown_service", "kubernetes")
        assert len(recs) >= 1
        assert "No specific exporter" in notes

    def test_build_deployment_manifests(self):
        workload, svc = build_exporter_manifests("postgres_exporter", "monitoring")
        assert workload["kind"] == "Deployment"
        assert svc["kind"] == "Service"
        assert workload["metadata"]["name"] == "postgres-exporter"

    def test_build_daemonset_manifests(self):
        workload, svc = build_exporter_manifests("node_exporter", "monitoring")
        assert workload["kind"] == "DaemonSet"

    def test_build_unknown_exporter_raises(self):
        with pytest.raises(ValueError, match="Unknown exporter_type"):
            build_exporter_manifests("nonexistent_exporter", "monitoring")

    def test_build_servicemonitor(self):
        manifest = build_servicemonitor_manifest(
            name="test-monitor", namespace="default",
            service_name="my-app", interval="15s",
        )
        assert manifest["kind"] == "ServiceMonitor"
        assert manifest["spec"]["endpoints"][0]["interval"] == "15s"
