"""Comprehensive unit tests for all granular tool modules (v4 refactor).

Tests all 28 granular tools across 9 tool groups.

v4 changes:
- Removed TestDiscoveryTools (prom_list_backends, prom_get_backend_status → resources)
- Removed TestDiagnosticsTools (prom_get_cardinality, prom_get_runtime_config → resources)
- Removed test_list_exporters (prom_list_exporters → prom://exporters/catalog resource)
- Removed test_list_rule_groups* (prom_list_rule_groups → prom://rules/groups resource)
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from prometheus_mcp_server.tools.query.query_tools import QueryTools
from prometheus_mcp_server.tools.onboarding.onboarding_tools import OnboardingTools
from prometheus_mcp_server.tools.exporter.exporter_tools import ExporterTools
from prometheus_mcp_server.tools.scrape_config.scrape_config_tools import ScrapeConfigTools
from prometheus_mcp_server.tools.tsdb_finops.tsdb_finops_tools import TsdbFinOpsTools
from prometheus_mcp_server.tools.rules.rules_tools import RulesTools
from prometheus_mcp_server.tools.promtool.promtool_tools import PromtoolTools
from prometheus_mcp_server.tools.simulation.simulation_tools import SimulationTools
from prometheus_mcp_server.tools.authoring.authoring_tools import AuthoringTools
from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.models.backend import BackendInfo, BackendCapabilities
from prometheus_mcp_server.models.query import (
    InstantQueryResult, InstantSample, ValidatePromQLResult, LabelTopologyResult,
    RangeQueryResult, RangeSeries, DownsamplingMetadata,
)
from prometheus_mcp_server.models.metadata import (
    CardinalitySummary, CardinalityOverview, TopCardinalityMetric, RuntimeConfig,
)


# ---- Helpers ----

def _sl(prometheus_service=None, kubernetes_service=None, config=None):
    return {
        "prometheus_service": prometheus_service or MagicMock(),
        "kubernetes_service": kubernetes_service or MagicMock(),
        "config": config or MagicMock(),
    }

def _ctx():
    ctx = MagicMock()
    ctx.info = ctx.warning = ctx.error = AsyncMock()
    return ctx

def _register(tool_instance):
    mcp = MagicMock()
    captured = {}
    def capture_tool(**kwargs):
        def decorator(fn):
            captured[fn.__name__] = fn
            return fn
        return decorator
    mcp.tool = capture_tool
    tool_instance.register(mcp)
    return captured


# ==========================================
# Query Tools (4 granular tools)
# ==========================================

class TestQueryTools:
    def setup_method(self):
        self.prom = MagicMock()
        self.tools = _register(QueryTools(_sl(prometheus_service=self.prom)))

    @pytest.mark.asyncio
    async def test_validate_promql(self):
        self.prom.validate_query = AsyncMock(return_value=ValidatePromQLResult(valid=True))
        result = await self.tools["prom_validate_promql"](
            backend_id="test", query="up", ctx=_ctx()
        )
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_query_instant(self):
        self.prom.enforce_counter_rule = AsyncMock()
        self.prom.instant_query = AsyncMock(
            return_value=InstantQueryResult(
                resultType="vector",
                result=[InstantSample(metric={"job": "test"}, value=(1.0, "1"))],
                sample_count=1,
            )
        )
        result = await self.tools["prom_query_instant"](
            backend_id="test", query="up", time=None, timeout=None,
            allow_raw_counters=False, ctx=_ctx()
        )
        assert result["resultType"] == "vector"

    @pytest.mark.asyncio
    async def test_query_range(self):
        self.prom.enforce_counter_rule = AsyncMock()
        self.prom.range_query = AsyncMock(
            return_value=RangeQueryResult(
                series=[RangeSeries(metric={"job": "test"}, values=[(1.0, "1")])],
                downsampling=DownsamplingMetadata(
                    strategy="average", original_step="15s", effective_step="15s",
                    max_points_per_series=200, original_point_count=100,
                    downsampled_point_count=100,
                ),
            )
        )
        result = await self.tools["prom_query_range"](
            backend_id="test", query="up", start=1000.0, end=2000.0,
            step=None, max_points_per_series=200, timeout=None,
            allow_raw_counters=False, ctx=_ctx()
        )
        assert "series" in result
        assert "downsampling" in result

    @pytest.mark.asyncio
    async def test_explore_labels(self):
        self.prom.explore_label_topology = AsyncMock(
            return_value=LabelTopologyResult(
                metric_name="up", label_names=["job"],
                label_values={"job": ["prom"]},
            )
        )
        result = await self.tools["prom_explore_labels"](
            backend_id="test", metric_name="up", ctx=_ctx()
        )
        assert result["metric_name"] == "up"


# ==========================================
# Onboarding Tools (3 granular tools)
# ==========================================

class TestOnboardingTools:
    def setup_method(self):
        self.tools = _register(OnboardingTools(_sl()))

    @pytest.mark.asyncio
    async def test_recommend_custom_app(self):
        result = await self.tools["prom_recommend_instrumentation"](
            workload_type="custom_app", language="python",
            framework=None, environment=None, ctx=_ctx()
        )
        assert result["strategy"] == "direct_instrumentation"

    @pytest.mark.asyncio
    async def test_recommend_postgres(self):
        result = await self.tools["prom_recommend_instrumentation"](
            workload_type="postgres", language=None,
            framework=None, environment=None, ctx=_ctx()
        )
        assert result["strategy"] == "exporter"

    @pytest.mark.asyncio
    async def test_recommend_spring_boot(self):
        result = await self.tools["prom_recommend_instrumentation"](
            workload_type="custom_app", language="java",
            framework="spring_boot", environment=None, ctx=_ctx()
        )
        assert result["strategy"] == "builtin_metrics"



    @pytest.mark.asyncio
    async def test_test_endpoint_requires_url(self):
        # prom_test_endpoint needs an actual endpoint_url field
        # Just verify tool exists
        assert "prom_test_endpoint" in self.tools


# ==========================================
# Exporter Tools (4 granular tools — v4: list moved to resource)
# ==========================================

class TestExporterTools:
    def setup_method(self):
        self.k8s = MagicMock()
        self.k8s.apply_deployment = AsyncMock()
        self.k8s.apply_daemonset = AsyncMock()
        self.k8s.apply_service = AsyncMock()
        self.k8s.delete_deployment = AsyncMock()
        self.k8s.delete_daemonset = AsyncMock()
        self.k8s.delete_service = AsyncMock()
        self.prom = MagicMock()
        self.tools = _register(ExporterTools(
            _sl(prometheus_service=self.prom, kubernetes_service=self.k8s)
        ))

    @pytest.mark.asyncio
    async def test_recommend_exporter(self):
        result = await self.tools["prom_recommend_exporter"](
            service_type="postgres", environment="kubernetes", ctx=_ctx()
        )
        assert len(result["exporters"]) >= 1

    @pytest.mark.asyncio
    async def test_install_exporter(self):
        result = await self.tools["prom_install_exporter"](
            exporter_type="postgres_exporter", namespace="monitoring",
            service_name=None, config=None, environment="kubernetes", ctx=_ctx()
        )
        assert len(result["applied_resources"]) == 2
        self.k8s.apply_deployment.assert_called_once()
        self.k8s.apply_service.assert_called_once()

    @pytest.mark.asyncio
    async def test_install_blackbox_exporter_config(self):
        # We need to test the manifest generation to see the configmap
        from prometheus_mcp_server.utils.exporter_catalog import build_exporter_manifests
        manifests = build_exporter_manifests(
            exporter_type="blackbox_exporter", namespace="monitoring"
        )
        # Find the configmap
        cm = next((m for m in manifests if m["kind"] == "ConfigMap"), None)
        assert cm is not None
        assert "http_2xx" in cm["data"]["config.yml"]

    @pytest.mark.asyncio
    async def test_uninstall_exporter(self):
        result = await self.tools["prom_uninstall_exporter"](
            exporter_type="postgres_exporter", namespace="monitoring",
            service_name=None, ctx=_ctx()
        )
        assert "removed_resources" in result


# ==========================================
# Scrape Config Tools (2 granular tools)
# ==========================================

class TestScrapeConfigTools:
    def setup_method(self):
        self.k8s = MagicMock()
        self.k8s.apply_servicemonitor = AsyncMock()
        self.k8s.get_servicemonitor_required_labels = AsyncMock(return_value={})
        self.k8s.discover_service_details = AsyncMock(return_value=None)
        self.tools = _register(ScrapeConfigTools(
            _sl(kubernetes_service=self.k8s)
        ))

    @pytest.mark.asyncio
    async def test_apply_servicemonitor(self):
        result = await self.tools["prom_apply_servicemonitor"](
            service_name="my-app", namespace="default",
            monitor_name=None, port_name="metrics",
            path="/metrics", interval="30s", labels=None, metric_relabelings=None, ctx=_ctx()
        )
        assert "ServiceMonitor" in result["applied"]
        self.k8s.apply_servicemonitor.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_probe(self):
        self.k8s.get_probe_required_labels = AsyncMock(return_value={})
        self.k8s.apply_custom_resource = AsyncMock()
        result = await self.tools["prom_apply_probe"](
            targets=["https://talkops.ai"], namespace="monitoring",
            probe_name=None, module="http_2xx", prober_url="blackbox:9115",
            interval="60s", labels=None, ctx=_ctx()
        )
        assert "Probe" in result["applied"]
        self.k8s.apply_custom_resource.assert_called_once()

    @pytest.mark.asyncio
    async def test_manage_file_sd_add(self, tmp_path):
        sd_file = tmp_path / "targets.json"
        sd_file.write_text("[]")
        result = await self.tools["prom_manage_file_sd"](
            file_sd_path=str(sd_file), targets=["host1:9100"],
            file_sd_action="add", target_labels=None,
            backend_id=None, ctx=_ctx()
        )
        assert result["action"] == "add"
        assert "host1:9100" in result["targets_added"]

    @pytest.mark.asyncio
    async def test_manage_file_sd_remove(self, tmp_path):
        sd_file = tmp_path / "targets.json"
        sd_file.write_text(json.dumps([{"targets": ["host1:9100"], "labels": {}}]))
        result = await self.tools["prom_manage_file_sd"](
            file_sd_path=str(sd_file), targets=["host1:9100"],
            file_sd_action="remove", target_labels=None,
            backend_id=None, ctx=_ctx()
        )
        assert result["action"] == "remove"
        data = json.loads(sd_file.read_text())
        assert len(data) == 0


# ==========================================
# TSDB FinOps Tools (4 granular tools)
# ==========================================

class TestTsdbFinOpsTools:
    def setup_method(self):
        self.prom = MagicMock()
        self.tools = _register(TsdbFinOpsTools(_sl(prometheus_service=self.prom)))

    @pytest.mark.asyncio
    async def test_plan_relabel_drop_metric(self):
        result = await self.tools["prom_plan_relabel"](
            backend_id="test", metric_name="expensive_metric",
            labels_to_drop=None, labels_to_keep=None, regex_filter=None, ctx=_ctx()
        )
        assert result["relabel_configs"][0]["action"] == "drop"
        assert "yaml" in result

    @pytest.mark.asyncio
    async def test_plan_relabel_drop_labels(self):
        result = await self.tools["prom_plan_relabel"](
            backend_id="test", metric_name="http_requests_total",
            labels_to_drop=["user_id", "request_id"],
            labels_to_keep=None, regex_filter=None, ctx=_ctx()
        )
        assert len(result["relabel_configs"]) == 2
        assert result["relabel_configs"][0]["action"] == "labeldrop"

    @pytest.mark.asyncio
    async def test_plan_relabel_keep_labels(self):
        result = await self.tools["prom_plan_relabel"](
            backend_id="test", metric_name=None,
            labels_to_drop=None, labels_to_keep=["job", "namespace"],
            regex_filter=None, ctx=_ctx()
        )
        assert result["relabel_configs"][0]["action"] == "labelkeep"

    @pytest.mark.asyncio
    async def test_optimize_cardinality(self):
        self.prom.get_cardinality_summary = AsyncMock(
            return_value=CardinalitySummary(
                overview=CardinalityOverview(total_series=50000),
                top_cardinality_metrics=[
                    TopCardinalityMetric(metric_name="http_requests_total", series_count=5000),
                ],
            )
        )
        result = await self.tools["prom_optimize_cardinality"](
            backend_id="test", metric_name="http_requests_total",
            top_n=10, ctx=_ctx()
        )
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_create_recording_rule(self):
        result = await self.tools["prom_create_recording_rule"](
            backend_id="test",
            rule_name="job:http_requests:rate5m",
            rule_expr="sum by (job) (rate(http_requests_total[5m]))",
            rule_labels={"severity": "info"}, rule_interval=None, ctx=_ctx()
        )
        assert result["rule_group"]["rules"][0]["record"] == "job:http_requests:rate5m"
        assert "yaml" in result

    @pytest.mark.asyncio
    async def test_configure_remote_write(self):
        result = await self.tools["prom_configure_remote_write"](
            backend_id="test",
            remote_url="http://thanos:19291/api/v1/receive",
            remote_name="thanos", write_relabel_configs=None,
            queue_config=None, ctx=_ctx()
        )
        assert result["remote_write_config"]["url"] == "http://thanos:19291/api/v1/receive"
        assert "yaml" in result


# ==========================================
# Rules Tools (4 granular tools — v4: list moved to resource)
# ==========================================

class TestRulesTools:
    def setup_method(self):
        self.prom = MagicMock()
        self.k8s = MagicMock()
        self.tools = _register(RulesTools(
            _sl(prometheus_service=self.prom, kubernetes_service=self.k8s)
        ))

    @pytest.mark.asyncio
    async def test_get_rule_group(self):
        self.prom.get_rule_group = AsyncMock(return_value={
            "name": "test_group", "rules": [{"alert": "Test"}]
        })
        result = await self.tools["prom_get_rule_group"](
            backend_id="test", group_name="test_group",
            file_filter=None, ctx=_ctx()
        )
        assert result["name"] == "test_group"

    @pytest.mark.asyncio
    async def test_get_rule_group_not_found(self):
        self.prom.get_rule_group = AsyncMock(return_value=None)
        with pytest.raises(PrometheusOperationError, match="not found"):
            await self.tools["prom_get_rule_group"](
                backend_id="test", group_name="nonexistent",
                file_filter=None, ctx=_ctx()
            )

    @pytest.mark.asyncio
    async def test_upsert_rule_group_yaml_output(self):
        result = await self.tools["prom_upsert_rule_group"](
            backend_id="test", group_name="test_group",
            rules=[{"alert": "HighCPU", "expr": "cpu > 90"}],
            interval=None, namespace="monitoring",
            storage_mode="yaml_output", ctx=_ctx()
        )
        assert result["applied"] is False
        assert "yaml" in result
        assert "groups" in result["yaml"]

    @pytest.mark.asyncio
    async def test_delete_rule_group(self):
        self.k8s.delete_custom_resource = AsyncMock()
        result = await self.tools["prom_delete_rule_group"](
            backend_id="test", group_name="test_group",
            namespace="monitoring", storage_mode="k8s_crd", ctx=_ctx()
        )
        assert result["group_name"] == "test_group"

    @pytest.mark.asyncio
    async def test_describe_alert_rule(self):
        self.prom.get_rule_group = AsyncMock(return_value={
            "name": "test_group",
            "rules": [{
                "alert": "HighCPU", "expr": "cpu > 90", "for": "5m",
                "labels": {"severity": "critical"},
                "annotations": {"summary": "CPU is high"},
                "state": "inactive",
            }]
        })
        result = await self.tools["prom_describe_alert_rule"](
            backend_id="test", group_name="test_group",
            alert_name="HighCPU", ctx=_ctx()
        )
        assert result["alert_name"] == "HighCPU"
        assert "explanation" in result


# ==========================================
# Promtool Tools (2 granular tools)
# ==========================================

class TestPromtoolTools:
    def setup_method(self):
        self.tools = _register(PromtoolTools(_sl()))

    @pytest.mark.asyncio
    async def test_check_rule_group_exists(self):
        assert "prom_check_rule_group" in self.tools

    @pytest.mark.asyncio
    async def test_run_rule_tests_exists(self):
        assert "prom_run_rule_tests" in self.tools


# ==========================================
# Simulation Tools (3 granular tools)
# ==========================================

class TestSimulationTools:
    def setup_method(self):
        self.prom = MagicMock()
        self.tools = _register(SimulationTools(_sl(prometheus_service=self.prom)))

    @pytest.mark.asyncio
    async def test_simulate_firing_historical_no_fire(self):
        self.prom.evaluate_rule_expr = AsyncMock(return_value=[])
        result = await self.tools["prom_simulate_firing_historical"](
            backend_id="test", expr="cpu > 90", for_duration="5m",
            start=1000.0, end=2000.0, step="1m", ctx=_ctx()
        )
        assert result["would_fire"] is False
        assert result["firing_windows"] == []

    @pytest.mark.asyncio
    async def test_analyze_firing_history_no_firings(self):
        self.prom.get_alerts_for_state = AsyncMock(return_value=[])
        result = await self.tools["prom_analyze_firing_history"](
            backend_id="test", alert_name="TestAlert",
            lookback_hours=24, ctx=_ctx()
        )
        assert result["total_firings"] == 0
        assert "no firings" in result["recommendation"].lower()

    @pytest.mark.asyncio
    async def test_simulate_synthetic_exists(self):
        assert "prom_simulate_firing_synthetic" in self.tools


# ==========================================
# Authoring Tools (3 granular tools)
# ==========================================

class TestAuthoringTools:
    def setup_method(self):
        self.prom = MagicMock()
        self.tools = _register(AuthoringTools(_sl(prometheus_service=self.prom)))

    @pytest.mark.asyncio
    async def test_draft_alert_error_rate(self):
        result = await self.tools["prom_draft_alert_rule"](
            intent="alert when error rate exceeds 5%",
            metric="http_errors_total", threshold=0.05,
            severity="critical", for_duration=None, template=None, ctx=_ctx()
        )
        assert result["template_used"] == "high_error_rate"
        assert "rule_group_yaml" in result
        assert result["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_draft_alert_cpu(self):
        result = await self.tools["prom_draft_alert_rule"](
            intent="alert on high CPU usage",
            metric=None, threshold=80, severity=None,
            for_duration=None, template=None, ctx=_ctx()
        )
        assert result["template_used"] == "high_cpu"

    @pytest.mark.asyncio
    async def test_draft_alert_explicit_template(self):
        result = await self.tools["prom_draft_alert_rule"](
            intent="monitor disk", metric=None, threshold=10,
            severity="warning", for_duration="15m",
            template="disk_space", ctx=_ctx()
        )
        assert result["template_used"] == "disk_space"
        assert result["for_duration"] == "15m"

    @pytest.mark.asyncio
    async def test_tune_alert_rule(self):
        self.prom.get_alerts_for_state = AsyncMock(return_value=[])
        result = await self.tools["prom_tune_alert_rule"](
            backend_id="test", alert_name="TestAlert",
            current_expr="cpu > 90", current_for="5m",
            current_threshold=90, lookback_hours=24, ctx=_ctx()
        )
        assert result["alert_name"] == "TestAlert"
        assert len(result["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_suggest_promql_cpu(self):
        result = await self.tools["prom_suggest_promql"](
            intent="CPU usage per pod", metric_hints=None, ctx=_ctx()
        )
        assert "query" in result
        assert "cpu" in result["query"].lower()

    @pytest.mark.asyncio
    async def test_suggest_promql_errors(self):
        result = await self.tools["prom_suggest_promql"](
            intent="error rate for my service",
            metric_hints=["http_requests_total"], ctx=_ctx()
        )
        assert "query" in result
        assert "5xx" in result["query"] or "error" in result["explanation"].lower()

    @pytest.mark.asyncio
    async def test_suggest_promql_health(self):
        result = await self.tools["prom_suggest_promql"](
            intent="which targets are down", metric_hints=None, ctx=_ctx()
        )
        assert "up" in result["query"]
