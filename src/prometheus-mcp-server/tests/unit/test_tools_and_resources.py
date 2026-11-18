"""Unit tests for all 19 MCP tools and 11 dynamic `prom://` resources."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Callable, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic.fields import FieldInfo

from prometheus_mcp_server.config import BackendConfig, KubernetesConfig, ServerConfig
from prometheus_mcp_server.models.backend import BackendCapabilities, BackendInfo
from prometheus_mcp_server.models.metadata import MetricCatalog, MetricMetadata
from prometheus_mcp_server.models.query import (
    DownsamplingMetadata,
    InstantQueryResult,
    InstantSample,
    LabelTopologyResult,
    RangeQueryResult,
    RangeSeries,
)
from prometheus_mcp_server.models.target import (
    FailedTargetsSummary,
    ServiceInfo,
    ServiceTopology,
)
from prometheus_mcp_server.resources import initialize_resources
from prometheus_mcp_server.tools import initialize_tools


def _capture_tools(service_locator: Dict[str, Any]) -> Dict[str, Callable[..., Any]]:
    mcp = MagicMock()
    captured: Dict[str, Callable[..., Any]] = {}

    def tool_decorator(**_kwargs: Any):
        def _wrap(fn: Callable[..., Any]):
            sig = inspect.signature(fn)

            async def _invoker(*args: Any, **kwargs: Any) -> Any:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                resolved_kwargs: Dict[str, Any] = {}
                for k, v in bound.arguments.items():
                    if isinstance(v, FieldInfo):
                        resolved_kwargs[k] = v.default
                    else:
                        resolved_kwargs[k] = v
                return await fn(**resolved_kwargs)

            captured[fn.__name__] = _invoker
            return fn

        return _wrap

    mcp.tool = tool_decorator
    reg = initialize_tools(service_locator)
    reg.register_all_tools(mcp)
    return captured


def _capture_resources(service_locator: Dict[str, Any]) -> Dict[str, Callable[..., Any]]:
    mcp = MagicMock()
    captured: Dict[str, Callable[..., Any]] = {}

    def resource_decorator(uri: str, **_kwargs: Any):
        def _wrap(fn: Callable[..., Any]):
            captured[uri] = fn
            return fn

        return _wrap

    mcp.resource = resource_decorator
    reg = initialize_resources(service_locator)
    reg.register_all_resources(mcp)
    return captured


@pytest.fixture
def mocked_locator() -> Dict[str, Any]:
    cfg = ServerConfig(
        allow_write=True,
        backends=[BackendConfig(id="default", base_url="http://localhost:9090")],
        kubernetes=KubernetesConfig(enabled=True),
    )
    prom_svc = MagicMock()
    prom_svc.list_backends.return_value = [
        BackendInfo(
            id="default",
            type="prometheus",
            display_name="default",
            base_url="http://localhost:9090",
            health="healthy",
        )
    ]
    prom_svc.check_health = AsyncMock(return_value="healthy")
    prom_svc.get_backend_capabilities = AsyncMock(
        return_value=BackendCapabilities(
            backend=BackendInfo(
                id="default",
                type="prometheus",
                display_name="default",
                base_url="http://localhost:9090",
                health="healthy",
                version="3.0.1",
            ),
            runtimeinfo={"storageRetention": "15d"},
            features={},
        )
    )
    prom_svc.get_targets = AsyncMock(
        return_value={
            "activeTargets": [
                {
                    "labels": {"job": "api", "instance": "10.0.0.1:8080"},
                    "health": "up",
                    "lastError": "",
                    "scrapePool": "api",
                },
                {
                    "labels": {"job": "db", "instance": "10.0.0.2:9187"},
                    "health": "down",
                    "lastError": "connection refused",
                    "scrapePool": "db",
                },
            ]
        }
    )
    prom_svc.get_tsdb_status = AsyncMock(
        return_value={
            "headStats": {"numSeries": 25000, "numLabelPairs": 4000, "chunkCount": 80000},
            "seriesCountByMetricName": [
                {"name": "http_request_duration_seconds_bucket", "value": 8000},
                {"name": "unused_debug_metric", "value": 6000},
            ],
            "labelValueCountByLabelName": [
                {"name": "user_id", "value": 3500},
                {"name": "job", "value": 12},
            ],
            "seriesCountByLabelValuePair": [{"name": "user_id=u1", "value": 100}],
        }
    )
    prom_svc.get_wal_replay = AsyncMock(return_value={"min": 1, "max": 10, "current": 10})
    prom_svc.get_flags = AsyncMock(return_value={"web.enable-lifecycle": "true"})
    prom_svc.list_rule_groups = AsyncMock(
        return_value={
            "groups": [
                {
                    "name": "api-rules",
                    "rules": [
                        {
                            "alert": "HighLatency",
                            "expr": "histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m]))) > 1",
                        }
                    ],
                }
            ]
        }
    )
    prom_svc.get_rule_group = AsyncMock(
        return_value={
            "name": "api-rules",
            "rules": [{"alert": "HighLatency", "expr": "up == 0"}],
        }
    )
    prom_svc.get_metric_catalog = AsyncMock(
        return_value=MetricCatalog(
            metrics=[
                MetricMetadata(
                    name="http_requests_total",
                    type="counter",
                    help="Total HTTP requests",
                ),
                MetricMetadata(name="up", type="gauge", help="Target up"),
            ],
            total_count=2,
        )
    )
    prom_svc.get_series = AsyncMock(
        return_value=[{"__name__": "up", "job": "api", "instance": "10.0.0.1:8080"}]
    )
    prom_svc.explore_label_topology = AsyncMock(
        return_value=LabelTopologyResult(
            metric_name="http_requests_total",
            label_names=["job", "status"],
            label_values={"job": ["api"], "status": ["200", "500"]},
        )
    )
    prom_svc.enforce_counter_rule = AsyncMock(return_value=None)
    prom_svc.instant_query = AsyncMock(
        return_value=InstantQueryResult(
            resultType="vector",
            result=[
                InstantSample(
                    metric={"__name__": "up", "job": "api", "instance": "10.0.0.1:8080"},
                    value=(1700000000.0, "1"),
                )
            ],
            eval_time_seconds=0.012,
            sample_count=1,
            truncated=False,
        )
    )
    prom_svc.range_query = AsyncMock(
        return_value=RangeQueryResult(
            series=[
                RangeSeries(
                    metric={"__name__": "up", "job": "api"},
                    values=[(1700000000.0, "10.0"), (1700000060.0, "20.0")],
                )
            ],
            downsampling=DownsamplingMetadata(
                strategy="average",
                original_step="1m",
                effective_step="1m",
                max_points_per_series=120,
                original_point_count=2,
                downsampled_point_count=2,
            ),
        )
    )
    prom_svc.query_exemplars = AsyncMock(
        return_value=[
            {
                "trace_id": "trace-abc-123",
                "span_id": "span-001",
                "value": 1.45,
                "timestamp": 1700000030.0,
                "exemplar_labels": {"traceID": "trace-abc-123"},
                "series_labels": {"job": "api"},
            }
        ]
    )
    prom_svc.get_alerts = AsyncMock(
        return_value=[
            {
                "labels": {"alertname": "HighErrorRate", "severity": "critical", "job": "api"},
                "annotations": {"summary": "Error rate > 5%"},
                "state": "firing",
                "activeAt": "2026-11-04T12:00:00Z",
                "value": "0.08",
            }
        ]
    )
    prom_svc.get_alerts_for_state = AsyncMock(
        return_value=[
            {
                "metric": {"alertname": "HighErrorRate"},
                "values": [(1700000000.0, "1"), (1700000060.0, "1")],
            }
        ]
    )
    prom_svc.evaluate_rule_expr = AsyncMock(
        return_value=[
            {
                "metric": {"job": "api"},
                "values": [
                    (1700000000.0 + i * 60.0, "0.08") for i in range(10)
                ],
            }
        ]
    )
    prom_svc.reload_config = AsyncMock(return_value=True)
    prom_svc.get_service_topology = AsyncMock(
        return_value=ServiceTopology(
            services=[
                ServiceInfo(
                    service_id="default/api",
                    display_name="api",
                    backend_id="default",
                    job="api",
                    targets_up=1,
                    targets_total=1,
                )
            ]
        )
    )
    prom_svc.get_failed_targets = AsyncMock(
        return_value=FailedTargetsSummary(failed_targets=[])
    )

    k8s_svc = MagicMock()
    k8s_svc.get_servicemonitor_required_labels = AsyncMock(
        return_value={"release": "kube-prometheus-stack"}
    )
    k8s_svc.get_probe_required_labels = AsyncMock(
        return_value={"release": "kube-prometheus-stack"}
    )
    k8s_svc.apply_custom_resource = AsyncMock()
    k8s_svc.delete_custom_resource = AsyncMock()
    k8s_svc._resolve_crd_coords = MagicMock(
        return_value=("monitoring.coreos.com", "v1", "servicemonitors")
    )
    k8s_svc.upsert_rule_group_crd = AsyncMock(
        return_value={
            "action": "updated",
            "crd_name": "api-rules",
            "namespace": "monitoring",
            "group_name": "api-rules",
            "sibling_group_count": 1,
            "manifest": {"kind": "PrometheusRule"},
        }
    )
    k8s_svc.delete_rule_group_crd = AsyncMock(
        return_value={
            "found": True,
            "action": "removed_group_from_crd",
            "crd_name": "api-rules",
            "namespace": "monitoring",
            "group_name": "api-rules",
            "remaining_group_count": 1,
        }
    )
    k8s_svc.apply_deployment = AsyncMock()
    k8s_svc.apply_daemonset = AsyncMock()
    k8s_svc.apply_service = AsyncMock()
    k8s_svc.apply_servicemonitor = AsyncMock()
    k8s_svc.apply_configmap = AsyncMock()
    k8s_svc.apply_serviceaccount = AsyncMock()
    k8s_svc.apply_clusterrole = AsyncMock()
    k8s_svc.apply_clusterrolebinding = AsyncMock()
    k8s_svc.delete_deployment = AsyncMock()
    k8s_svc.delete_daemonset = AsyncMock()
    k8s_svc.delete_service = AsyncMock()
    k8s_svc.delete_servicemonitor = AsyncMock()
    k8s_svc.list_scrape_crds = AsyncMock(
        return_value={"ServiceMonitor": [{"kind": "ServiceMonitor", "name": "api-sm", "namespace": "monitoring"}]}
    )
    k8s_svc.list_prometheus_rules = AsyncMock(return_value={"items": []})
    k8s_svc.get_crd_manifest = AsyncMock(
        return_value={"kind": "ServiceMonitor", "metadata": {"name": "api-sm", "namespace": "monitoring"}}
    )

    return {
        "prometheus_service": prom_svc,
        "kubernetes_service": k8s_svc,
        "config": cfg,
    }


class TestAll19ToolsAnd11Resources:
    @pytest.mark.asyncio
    async def test_diagnostics_toolset(self, mocked_locator: Dict[str, Any]) -> None:
        tools = _capture_tools(mocked_locator)

        diag = await tools["prom_get_diagnostics"](
            backend_id="default", include="all", scrape_pool=None, detail="summary"
        )
        assert diag["health"] == "healthy"
        assert diag["targets_summary"]["down_count"] == 1
        assert any(o["code"] == "TARGETS_DOWN" for o in diag["observations"])

        card = await tools["prom_analyze_cardinality"](
            backend_id="default",
            metric_prefix=None,
            focus_label="user_id",
            top_n=10,
            check_unused_rules=True,
        )
        obs_codes = {o["code"] for o in card["observations"]}
        assert "HISTOGRAM_BUCKET_EXPLOSION" in obs_codes
        assert "UNREFERENCED_HIGH_COST_METRIC" in obs_codes
        assert "UNBOUNDED_LABEL_FANOUT" in obs_codes

    @pytest.mark.asyncio
    async def test_query_toolset(self, mocked_locator: Dict[str, Any]) -> None:
        tools = _capture_tools(mocked_locator)

        exp = await tools["prom_explore_metrics"](
            backend_id="default",
            metric_pattern="http",
            label_name="http_requests_total",
            match_selector=None,
            limit=10,
            cursor=None,
        )
        assert exp["total_matched"] == 1
        assert "label_topology" in exp

        inst = await tools["prom_query_instant"](
            backend_id="default",
            query="up",
            time=None,
            timeout="15s",
            limit=10,
            detail="summary",
        )
        assert inst["series_count"] == 1
        assert inst["series"][0]["value"] == 1.0

        rng = await tools["prom_query_range"](
            backend_id="default",
            query="up",
            start="-15m",
            end="now",
            step="1m",
            include_chart=True,
            limit=10,
            detail="summary",
        )
        assert rng["series"][0]["stats"]["avg"] == 15.0
        assert "chart" in rng

        ex = await tools["prom_query_exemplars"](
            backend_id="default",
            query='http_request_duration_seconds_bucket{job="api"}',
            start="-15m",
            end="now",
            limit=10,
        )
        assert ex["trace_ids"] == ["trace-abc-123"]

        cmp_res = await tools["prom_compare_periods"](
            backend_id="default",
            query="rate(http_requests_total[5m])",
            current_start="-15m",
            current_end="now",
            baseline_offset="1h",
            step="1m",
        )
        assert len(cmp_res["comparisons"]) == 1

        red = await tools["prom_analyze_service_red"](
            backend_id="default",
            service_selector='job="api"',
            lookback="15m",
            metric_convention="auto",
            include_exemplars=True,
        )
        assert red["request_rate_rps"] == 1.0
        assert len(red["exemplars"]) == 1

        slo = await tools["prom_evaluate_slo_burn"](
            backend_id="default",
            error_query="rate(err_total[5m])",
            total_query="rate(req_total[5m])",
            slo_target=0.999,
            window_days=30,
        )
        assert "burn_rate_multiplier" in slo
        assert len(slo["observations"]) == 1

    @pytest.mark.asyncio
    async def test_rules_toolset(self, mocked_locator: Dict[str, Any]) -> None:
        tools = _capture_tools(mocked_locator)

        firing = await tools["prom_get_firing_alerts"](
            backend_id="default",
            alert_name="HighErrorRate",
            state="firing",
            label_filters=None,
            include_history_lookback="24h",
            limit=20,
        )
        assert firing["active_count"] == 1
        assert firing["history_stats"]["episode_count"] == 1

        with patch(
            "prometheus_mcp_server.tools.rules.rules_tools.is_promtool_available",
            return_value=False,
        ):
            val = await tools["prom_validate_rules"](
                rule_group={
                    "name": "api-rules",
                    "interval": "1m",
                    "rules": [
                        {
                            "alert": "HighErrorRate",
                            "expr": "job:errors:rate5m > 0.05",
                            "for": "5m",
                            "labels": {"severity": "critical"},
                            "annotations": {"summary": "High errors"},
                        }
                    ],
                },
                unit_tests=None,
                check_hygiene=True,
            )
            assert val["valid"] is True
            assert val["hygiene_observations"] == []

        sim = await tools["prom_simulate_rule_firing"](
            backend_id="default",
            rule={"alert": "HighErrorRate", "expr": "job:errors:rate5m > 0.05", "for": "5m"},
            mode="historical",
            start="-1h",
            end="now",
            step="1m",
            synthetic_series=None,
        )
        assert sim["would_fire"] is True
        assert sim["total_firing_episodes"] >= 1

        with patch(
            "prometheus_mcp_server.tools.rules.rules_tools.is_promtool_available",
            return_value=False,
        ):
            up_res = await tools["prom_upsert_rule_group"](
                backend_id="default",
                group={
                    "name": "api-rules",
                    "rules": [{"record": "job:req:rate5m", "expr": "rate(req_total[5m])"}],
                },
                namespace="monitoring",
                crd_name=None,
                labels=None,
                dry_run=False,
                confirm=True,
            )
            assert up_res["status"] == "applied"
            assert up_res["sibling_group_count"] == 1

        del_res = await tools["prom_delete_rule_group"](
            backend_id="default",
            group_name="api-rules",
            namespace="monitoring",
            crd_name=None,
            dry_run=False,
            confirm=True,
        )
        assert del_res["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_scrape_and_exporter_toolsets_including_bug_fixes(
        self, mocked_locator: Dict[str, Any], tmp_path: Path
    ) -> None:
        tools = _capture_tools(mocked_locator)

        # Bug fix check: when `up == 0.0`, prom_verify_metrics_endpoint MUST report healthy=False, scrape_up=False!
        mocked_locator["prometheus_service"].instant_query = AsyncMock(
            return_value=InstantQueryResult(
                resultType="vector",
                result=[
                    InstantSample(
                        metric={"__name__": "up", "job": "broken-exporter", "instance": "10.0.0.9:9100"},
                        value=(1700000000.0, "0"),
                    )
                ],
                eval_time_seconds=0.01,
                sample_count=1,
            )
        )
        down_verify = await tools["prom_verify_metrics_endpoint"](
            backend_id="default",
            endpoint_url=None,
            job_label="broken-exporter",
            expected_metrics=None,
            verify_timeout=1,
        )
        assert down_verify["healthy"] is False
        assert down_verify["scrape_up"] is False
        assert down_verify["down_instances"] == ["10.0.0.9:9100"]

        # Bug fix check: file_sd apply triggers POST /-/reload
        sd_file = tmp_path / "targets.json"
        sd_res = await tools["prom_apply_scrape_config"](
            backend_id="default",
            kind="file_sd",
            name="node-targets",
            spec={
                "file_path": str(sd_file),
                "targets": ["10.0.0.5:9100"],
                "labels": {"job": "node"},
                "trigger_reload": True,
            },
            namespace="monitoring",
            dry_run=False,
            confirm=True,
        )
        assert sd_res["status"] == "applied"
        assert sd_res["reload_triggered"] is True
        assert sd_file.exists()

        # Exporter install & uninstall
        inst_res = await tools["prom_install_exporter"](
            exporter_type="redis_exporter",
            namespace="monitoring",
            release_name="redis-exp",
            exporter_config={"REDIS_ADDR": "redis://redis:6379", "REDIS_PASSWORD": "secret"},
            create_servicemonitor=True,
            dry_run=True,
            confirm=False,
        )
        assert inst_res["status"] == "dry_run_preview"
        assert "secret" not in json.dumps(inst_res["manifests"])

        uninst_res = await tools["prom_uninstall_exporter"](
            exporter_type="redis_exporter",
            namespace="monitoring",
            release_name="redis-exp",
            dry_run=False,
            confirm=True,
        )
        assert uninst_res["status"] == "uninstalled"

    @pytest.mark.asyncio
    async def test_all_11_dynamic_resources(
        self, mocked_locator: Dict[str, Any]
    ) -> None:
        from prometheus_mcp_server.models.metadata import (
            CardinalityOverview,
            CardinalitySummary,
            RuntimeConfig,
            TopCardinalityMetric,
        )

        mocked_locator["prometheus_service"].get_config = AsyncMock(
            return_value=RuntimeConfig(
                global_config={"scrape_interval": "15s"}, tsdb={"headStats": {"numSeries": 100}}
            )
        )
        mocked_locator["prometheus_service"].get_cardinality_summary = AsyncMock(
            return_value=CardinalitySummary(
                overview=CardinalityOverview(
                    total_series=100, head_series=100, num_label_pairs=20, memory_bytes=1024
                ),
                top_cardinality_metrics=[
                    TopCardinalityMetric(metric_name="up", series_count=10)
                ],
            )
        )

        resources = _capture_resources(mocked_locator)
        assert len(resources) == 11

        r_backends = json.loads(await resources["prom://system/backends"]())
        assert len(r_backends["backends"]) == 1

        r_caps = json.loads(
            await resources["prom://system/backends/{backend_id}"]("default")
        )
        assert r_caps["backend"]["id"] == "default"

        r_cfg = json.loads(await resources["prom://config/runtime"]())
        assert "default" in r_cfg

        r_tgts = json.loads(await resources["prom://topology/targets"]())
        assert "services" in r_tgts
        assert "failed_targets" in r_tgts

        r_cat = json.loads(await resources["prom://metadata/catalog"]())
        assert "default" in r_cat

        r_card = json.loads(await resources["prom://tsdb/cardinality"]())
        assert "default" in r_card

        r_groups = json.loads(await resources["prom://rules/groups"]())
        assert r_groups["default"]["total_groups"] == 1

        r_group = json.loads(
            await resources["prom://rules/{backend_id}/groups/{group_name}"](
                "default", "api-rules"
            )
        )
        assert r_group["group"]["name"] == "api-rules"

        r_crds = json.loads(await resources["prom://kubernetes/scrape-crds"]())
        assert "scrape_crds" in r_crds

        r_manifest = json.loads(
            await resources["prom://kubernetes/manifests/{kind}/{namespace}/{name}"](
                "ServiceMonitor", "monitoring", "api-sm"
            )
        )
        assert r_manifest["kind"] == "ServiceMonitor"

        r_audit = json.loads(await resources["prom://audit/recent"]())
        assert "entries" in r_audit

    @pytest.mark.asyncio
    async def test_rule_storage_modes_yaml_local_and_http_ruler(
        self, mocked_locator: Dict[str, Any], tmp_path: Path
    ) -> None:
        mocked_locator["prometheus_service"].upsert_ruler_group = AsyncMock(
            return_value={"status": "applied", "status_code": 202, "namespace": "prod"}
        )
        mocked_locator["prometheus_service"].delete_ruler_group = AsyncMock(
            return_value={"status": "deleted", "status_code": 202, "namespace": "prod"}
        )
        tools = _capture_tools(mocked_locator)

        with patch(
            "prometheus_mcp_server.tools.rules.rules_tools.is_promtool_available",
            return_value=False,
        ):
            # 1. yaml_only mode works even without Kubernetes
            yaml_res = await tools["prom_upsert_rule_group"](
                backend_id="default",
                group={
                    "name": "gitops-rules",
                    "rules": [{"record": "job:up:sum", "expr": "sum by (job) (up)"}],
                },
                namespace="monitoring",
                storage_mode="yaml_only",
            )
            assert yaml_res["status"] == "rendered"
            assert yaml_res["storage_mode"] == "yaml_only"
            assert "job:up:sum" in yaml_res["rules_yaml"]

            # 2. local_file mode with non-destructive multi-group merge
            rule_file = tmp_path / "prometheus.rules.yaml"
            await tools["prom_upsert_rule_group"](
                backend_id="default",
                group={
                    "name": "group-one",
                    "rules": [{"record": "job:one:sum", "expr": "sum(up)"}],
                },
                crd_name=str(rule_file),
                storage_mode="local_file",
                dry_run=False,
                confirm=True,
            )
            local_res2 = await tools["prom_upsert_rule_group"](
                backend_id="default",
                group={
                    "name": "group-two",
                    "rules": [{"record": "job:two:sum", "expr": "count(up)"}],
                },
                crd_name=str(rule_file),
                storage_mode="local_file",
                dry_run=False,
                confirm=True,
            )
            assert local_res2["status"] == "applied"
            assert local_res2["sibling_group_count"] == 1

            del_local = await tools["prom_delete_rule_group"](
                backend_id="default",
                group_name="group-one",
                crd_name=str(rule_file),
                storage_mode="local_file",
                dry_run=False,
                confirm=True,
            )
            assert del_local["status"] == "deleted"
            assert del_local["remaining_group_count"] == 1

            # 3. http_ruler mode (Mimir / Cortex / Thanos Ruler API)
            ruler_up = await tools["prom_upsert_rule_group"](
                backend_id="default",
                group={
                    "name": "mimir-group",
                    "rules": [{"record": "job:mimir:rate5m", "expr": "rate(req_total[5m])"}],
                },
                namespace="prod",
                storage_mode="http_ruler",
                dry_run=False,
                confirm=True,
            )
            assert ruler_up["status"] == "applied"
            assert ruler_up["storage_mode"] == "http_ruler"

            ruler_del = await tools["prom_delete_rule_group"](
                backend_id="default",
                group_name="mimir-group",
                namespace="prod",
                storage_mode="http_ruler",
                dry_run=False,
                confirm=True,
            )
            assert ruler_del["status"] == "deleted"
            assert ruler_del["storage_mode"] == "http_ruler"

    @pytest.mark.asyncio
    async def test_servicemonitor_k8s_service_autodiscovery_and_query_enhancements(
        self, mocked_locator: Dict[str, Any]
    ) -> None:
        mocked_locator["kubernetes_service"].discover_service_details = AsyncMock(
            return_value={
                "name": "checkout-svc",
                "namespace": "production",
                "labels": {
                    "app.kubernetes.io/name": "checkout",
                    "helm.sh/chart": "checkout-1.2.3",
                    "app.kubernetes.io/version": "1.2.3",
                },
                "selector": {"app.kubernetes.io/name": "checkout"},
                "ports": [{"name": "http-metrics", "port": 9090, "target_port": "9090", "protocol": "TCP"}],
                "metrics_port": {"name": "http-metrics", "port": 9090, "target_port": "9090", "protocol": "TCP"},
            }
        )
        from prometheus_mcp_server.models.target import ServiceMetricsList

        mocked_locator["prometheus_service"].get_service_metrics = AsyncMock(
            return_value=ServiceMetricsList(
                job="checkout",
                backend_id="default",
                metrics=[
                    MetricMetadata(
                        name="checkout_orders_total",
                        type="counter",
                        help="Total orders processed",
                    )
                ],
                total_count=1,
            )
        )
        tools = _capture_tools(mocked_locator)

        # 1. Auto-discovered ServiceMonitor with cross-namespace selector and stripped Helm labels
        sm_res = await tools["prom_apply_scrape_config"](
            backend_id="default",
            kind="ServiceMonitor",
            name="checkout-monitor",
            spec={
                "target_service": "checkout-svc",
                "target_namespace": "production",
                "path": "/metrics",
                "interval": "15s",
            },
            namespace="monitoring",
            dry_run=True,
            confirm=False,
        )
        spec_out = sm_res["manifest"]["spec"]
        assert spec_out["selector"]["matchLabels"] == {"app.kubernetes.io/name": "checkout"}
        assert spec_out["endpoints"][0]["port"] == "http-metrics"
        assert spec_out["namespaceSelector"] == {"matchNames": ["production"]}

        # 2. prom_query_instant(validate_only=True) preflight check
        val_ok = await tools["prom_query_instant"](
            backend_id="default",
            query='sum by (job) (rate(http_requests_total{job="api"}[5m]))',
            validate_only=True,
        )
        assert val_ok["validate_only"] is True
        assert val_ok["valid"] is True

        val_bad = await tools["prom_query_instant"](
            backend_id="default",
            query='sum(rate(http_requests_total{job="api"}[5m])',
            validate_only=True,
        )
        assert val_bad["valid"] is False
        assert val_bad["errors"]

        # 3. prom_explore_metrics(job="checkout") target metadata discovery
        job_metrics = await tools["prom_explore_metrics"](
            backend_id="default",
            job="checkout",
        )
        assert job_metrics["job"] == "checkout"
        assert job_metrics["metrics"][0]["name"] == "checkout_orders_total"

        # 4. prom_compare_periods z_score and anomaly_status
        cmp_res = await tools["prom_compare_periods"](
            backend_id="default",
            query="rate(http_requests_total[5m])",
        )
        assert "z_score" in cmp_res["comparisons"][0]
        assert "anomaly_status" in cmp_res["comparisons"][0]

        # 5. prom_evaluate_slo_burn multi_window_tiers
        slo_res = await tools["prom_evaluate_slo_burn"](
            backend_id="default",
            error_query='sum(rate(http_requests_total{status=~"5.."}[5m]))',
            total_query="sum(rate(http_requests_total[5m]))",
            slo_target=0.999,
            window_days=30,
        )
        assert len(slo_res["multi_window_tiers"]) == 4
        assert "error_budget_remaining_pct" in slo_res

    @pytest.mark.asyncio
    async def test_native_histograms_otel_utf8_istio_grpc_and_synthetic_simulation(
        self, mocked_locator: Dict[str, Any], tmp_path: Path
    ) -> None:
        mocked_locator["kubernetes_service"].apply_serviceaccount = AsyncMock()
        mocked_locator["kubernetes_service"].apply_clusterrole = AsyncMock()
        mocked_locator["kubernetes_service"].apply_clusterrolebinding = AsyncMock()
        mocked_locator["kubernetes_service"].apply_configmap = AsyncMock()
        tools = _capture_tools(mocked_locator)

        # 1. Native Histogram RED convention & OTel UTF-8 RED convention
        for conv, exp_fmt in [
            ("prometheus_native", "native"),
            ("otel_utf8", "native_utf8"),
            ("istio", "classic"),
            ("grpc", "classic"),
        ]:
            red_res = await tools["prom_analyze_service_red"](
                backend_id="default",
                service_selector='job="api"',
                lookback="5m",
                metric_convention=conv,
                include_exemplars=False,
            )
            assert red_res["metric_convention"] == conv
            assert red_res["histogram_format"] == exp_fmt
            assert red_res["latency_seconds"]["p95"] == 1.0

        # 2. Automatic Native Histogram fallback when classic _bucket returns empty
        async def _nh_fallback_query(backend_id: str, query: str, **_kwargs: Any) -> InstantQueryResult:
            if "_bucket" in query:
                return InstantQueryResult(
                    resultType="vector",
                    result=[],
                    eval_time_seconds=0.01,
                    sample_count=0,
                    truncated=False,
                )
            return InstantQueryResult(
                resultType="vector",
                result=[InstantSample(metric={"job": "api"}, value=(1700000000.0, "0.25"))],
                eval_time_seconds=0.01,
                sample_count=1,
                truncated=False,
            )

        mocked_locator["prometheus_service"].instant_query = AsyncMock(
            side_effect=_nh_fallback_query
        )
        red_auto_nh = await tools["prom_analyze_service_red"](
            backend_id="default",
            service_selector='job="api"',
            lookback="5m",
            metric_convention="auto",
            include_exemplars=False,
        )
        assert red_auto_nh["histogram_format"] == "native"
        assert red_auto_nh["latency_seconds"]["p95"] == 0.25

        # 3. Synthetic alert simulation mode
        with patch(
            "prometheus_mcp_server.tools.rules.rules_tools.is_promtool_available",
            return_value=False,
        ):
            syn_res = await tools["prom_simulate_rule_firing"](
                backend_id="default",
                rule={
                    "alert": "HighErrorRate",
                    "expr": "job:errors:ratio5m > 0.05",
                    "for": "5m",
                },
                mode="synthetic",
                step="1m",
                synthetic_series=[
                    {"series": 'job:errors:ratio5m{job="api"}', "values": "0.08+0x10"}
                ],
            )
            assert syn_res["mode"] == "synthetic"
            assert syn_res["synthetic_series_count"] == 1

        # 4. Delete scrape config (ServiceMonitor and file_sd)
        sd_file = tmp_path / "del_targets.json"
        sd_file.write_text(
            json.dumps([{"targets": ["10.0.0.1:9100"], "labels": {"job": "node"}}]),
            encoding="utf-8",
        )
        del_sd = await tools["prom_delete_scrape_config"](
            backend_id="default",
            kind="file_sd",
            name="node",
            namespace=str(sd_file),
            dry_run=False,
            confirm=True,
        )
        assert del_sd["status"] == "deleted"

        del_sm = await tools["prom_delete_scrape_config"](
            backend_id="default",
            kind="ServiceMonitor",
            name="api-sm",
            namespace="monitoring",
            dry_run=False,
            confirm=True,
        )
        assert del_sm["status"] == "deleted"

        # 5. Live exporter install across RBAC (kube-state-metrics), ConfigMap (blackbox_exporter), and haproxy_exporter
        for exp_type in ("kube-state-metrics", "blackbox_exporter", "haproxy_exporter"):
            inst_live = await tools["prom_install_exporter"](
                exporter_type=exp_type,
                namespace="monitoring",
                release_name=f"{exp_type}-rel",
                exporter_config={"HAPROXY_SCRAPE_URI": "http://haproxy:8404/stats;csv"},
                create_servicemonitor=True,
                dry_run=False,
                confirm=True,
            )
            assert inst_live["status"] == "installed"

    @pytest.mark.asyncio
    async def test_edge_cases_and_validation_guardrails(
        self, mocked_locator: Dict[str, Any]
    ) -> None:
        from prometheus_mcp_server.exceptions import PrometheusValidationError

        mocked_locator["prometheus_service"].get_series = AsyncMock(
            return_value=[
                {"__name__": "up", "job": "api", "instance": "1"},
                {"__name__": "up", "job": "api", "instance": "2"},
                {"__name__": "up", "job": "api", "instance": "3"},
            ]
        )
        tools = _capture_tools(mocked_locator)

        # 1. prom_explore_metrics match_selector pagination, label_name-only mode, and invalid regex fallback
        ms_res = await tools["prom_explore_metrics"](
            backend_id="default",
            match_selector='up{job="api"}',
            limit=1,
            cursor="0",
        )
        assert ms_res["total_returned"] == 1
        assert ms_res["next_cursor"] == "1"
        assert "_truncation_advice" in ms_res

        lbl_only = await tools["prom_explore_metrics"](
            backend_id="default",
            label_name="http_requests_total",
        )
        assert "label_topology" in lbl_only

        bad_rx = await tools["prom_explore_metrics"](
            backend_id="default",
            metric_pattern="[unclosed",
        )
        assert bad_rx["total_matched"] == 0

        # 2. prom_query_instant(validate_only=True) warnings & counter error
        mocked_locator["prometheus_service"].enforce_counter_rule = AsyncMock(
            side_effect=ValueError("Counter http_requests_total must be wrapped in rate()")
        )
        v_counter = await tools["prom_query_instant"](
            backend_id="default",
            query='histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job=~".*"}[5m]))',
            validate_only=True,
        )
        assert v_counter["valid"] is False
        assert any("Counter" in e for e in v_counter["errors"])
        assert len(v_counter["warnings"]) >= 2

        mocked_locator["prometheus_service"].enforce_counter_rule = AsyncMock(return_value=None)

        # 3. prom_query_range start >= end validation error & detail="full"
        with pytest.raises(PrometheusValidationError):
            await tools["prom_query_range"](
                backend_id="default",
                query="up",
                start="now",
                end="-1h",
            )
        rng_full = await tools["prom_query_range"](
            backend_id="default",
            query="up",
            start="-15m",
            end="now",
            detail="full",
        )
        assert "values" in rng_full["series"][0]

        # 4. prom_validate_rules hygiene observations & unit tests
        with patch(
            "prometheus_mcp_server.tools.rules.rules_tools.is_promtool_available",
            return_value=True,
        ), patch(
            "prometheus_mcp_server.tools.rules.rules_tools.check_rules",
            new=AsyncMock(return_value={"valid": True, "errors": [], "warnings": []}),
        ), patch(
            "prometheus_mcp_server.tools.rules.rules_tools.test_rules",
            new=AsyncMock(return_value={"passed": True, "output": "SUCCESS", "errors": []}),
        ):
            hygiene_res = await tools["prom_validate_rules"](
                rule_group={
                    "name": "hygiene-group",
                    "rules": [
                        {
                            "alert": "snake_case_alert",
                            "expr": "http_requests_total > 10",
                        },
                        {
                            "record": "invalid_recording_name",
                            "expr": "sum(up)",
                        },
                    ],
                },
                unit_tests=[
                    {
                        "interval": "1m",
                        "input_series": [{"series": "up", "values": "1+0x5"}],
                    }
                ],
                check_hygiene=True,
            )
            assert hygiene_res["valid"] is True
            assert len(hygiene_res["hygiene_observations"]) >= 2
            assert hygiene_res["unit_test_results"]["passed"] is True

        # 5. prom_verify_metrics_endpoint with direct endpoint_url probe
        with patch(
            "prometheus_mcp_server.tools.scrape_config.scrape_config_tools.test_metrics_endpoint",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "status_code": 200,
                    "metrics_found": ["up", "http_requests_total"],
                    "format": "prometheus",
                    "errors": [],
                }
            ),
        ):
            ep_verify = await tools["prom_verify_metrics_endpoint"](
                backend_id="default",
                endpoint_url="http://localhost:9100/metrics",
                job_label=None,
                expected_metrics=["up", "missing_metric"],
                verify_timeout=1,
            )
            assert ep_verify["endpoint_check"]["ok"] is True
            assert "missing_metric" in ep_verify["missing_metrics"]

        # 6. DaemonSet (node_exporter) and UDP Service (statsd_exporter) live install + invalid exporter error
        for exp_type in ("node_exporter", "statsd_exporter"):
            res_exp = await tools["prom_install_exporter"](
                exporter_type=exp_type,
                namespace="monitoring",
                dry_run=False,
                confirm=True,
            )
            assert res_exp["status"] == "installed"

        with pytest.raises(PrometheusValidationError):
            await tools["prom_install_exporter"](
                exporter_type="non_existent_exporter",
                namespace="monitoring",
            )
