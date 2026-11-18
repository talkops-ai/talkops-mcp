"""Unit tests for PrometheusService and KubernetesService (including multi-group PrometheusRule merge)."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from kubernetes.client.exceptions import ApiException

from prometheus_mcp_server.config import BackendConfig, KubernetesConfig, ServerConfig
from prometheus_mcp_server.services.kubernetes_service import KubernetesService
from prometheus_mcp_server.services.prometheus_service import PrometheusService


class TestPrometheusServiceUpgrades:
    @pytest.mark.asyncio
    @respx.mock
    async def test_tenant_header_and_query_exemplars(self) -> None:
        cfg = ServerConfig(
            backends=[
                BackendConfig(
                    id="mimir",
                    base_url="http://localhost:9090",
                    tenant_id="tenant-prod",
                )
            ]
        )
        svc = PrometheusService(cfg)

        route = respx.get("http://localhost:9090/api/v1/query_exemplars").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        {
                            "seriesLabels": {
                                "__name__": "http_request_duration_seconds_bucket",
                                "job": "checkout",
                            },
                            "exemplars": [
                                {
                                    "labels": {"traceID": "abc123trace", "spanID": "span1"},
                                    "value": "0.42",
                                    "timestamp": 1700000010.0,
                                },
                                {
                                    "labels": {"trace_id": "slow999trace", "span_id": "span2"},
                                    "value": "2.85",
                                    "timestamp": 1700000020.0,
                                },
                            ],
                        }
                    ],
                },
            )
        )

        exemplars = await svc.query_exemplars(
            "mimir",
            'http_request_duration_seconds_bucket{job="checkout"}',
            1700000000.0,
            1700000100.0,
        )
        assert route.called
        sent_req = route.calls[0].request
        assert sent_req.headers.get("X-Scope-OrgID") == "tenant-prod"
        # Sorted by highest value first
        assert len(exemplars) == 2
        assert exemplars[0]["trace_id"] == "slow999trace"
        assert exemplars[0]["value"] == 2.85
        assert exemplars[1]["trace_id"] == "abc123trace"
        await svc.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_series_alerts_flags_and_reload(self) -> None:
        svc = PrometheusService(ServerConfig())

        respx.get("http://localhost:9090/api/v1/series").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [{"__name__": "up", "job": "prometheus"}],
                },
            )
        )
        respx.get("http://localhost:9090/api/v1/alerts").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "alerts": [
                            {
                                "labels": {"alertname": "HighLatency", "severity": "critical"},
                                "state": "firing",
                                "activeAt": "2026-11-04T12:00:00Z",
                                "value": "1.25",
                            }
                        ]
                    },
                },
            )
        )
        respx.get("http://localhost:9090/api/v1/status/flags").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {"web.enable-lifecycle": "true"},
                },
            )
        )
        respx.post("http://localhost:9090/-/reload").mock(
            return_value=httpx.Response(200)
        )

        series = await svc.get_series("default", 'up{job="prometheus"}')
        assert len(series) == 1
        alerts = await svc.get_alerts("default")
        assert alerts[0]["labels"]["alertname"] == "HighLatency"
        flags = await svc.get_flags("default")
        assert flags["web.enable-lifecycle"] == "true"
        assert await svc.reload_config("default") is True
        await svc.close()


class TestKubernetesServiceMultiGroupMerge:
    @pytest.mark.asyncio
    async def test_upsert_and_delete_rule_group_preserves_sibling_groups(self) -> None:
        k8s = KubernetesService(KubernetesConfig(enabled=True))
        k8s._initialized = True
        k8s._custom = MagicMock()

        # Simulate an existing multi-group PrometheusRule CRD
        existing_crd: Dict[str, Any] = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusRule",
            "metadata": {
                "name": "platform-shared-rules",
                "namespace": "monitoring",
                "labels": {"release": "kube-prometheus-stack"},
            },
            "spec": {
                "groups": [
                    {
                        "name": "group-alpha",
                        "rules": [{"record": "job:alpha:rate5m", "expr": "rate(a_total[5m])"}],
                    },
                    {
                        "name": "group-beta",
                        "rules": [{"alert": "BetaDown", "expr": "up == 0"}],
                    },
                ]
            },
        }

        k8s._custom.list_cluster_custom_object.return_value = {"items": []}
        k8s._custom.list_namespaced_custom_object.return_value = {"items": [existing_crd]}
        k8s._custom.get_namespaced_custom_object.return_value = existing_crd

        updated_alpha = {
            "name": "group-alpha",
            "rules": [{"record": "job:alpha:rate5m", "expr": "sum(rate(a_total[5m]))"}],
        }

        # Upsert group-alpha without passing crd_name -> auto-discovers platform-shared-rules and keeps group-beta!
        res = await k8s.upsert_rule_group_crd(
            namespace="monitoring",
            rule_group=updated_alpha,
            crd_name=None,
            dry_run=False,
        )
        assert res["crd_name"] == "platform-shared-rules"
        assert res["sibling_group_count"] == 1
        groups_in_manifest = res["manifest"]["spec"]["groups"]
        assert len(groups_in_manifest) == 2
        assert {g["name"] for g in groups_in_manifest} == {"group-alpha", "group-beta"}
        assert res["manifest"]["metadata"]["labels"]["release"] == "kube-prometheus-stack"
        k8s._custom.patch_namespaced_custom_object.assert_called_once()

        # Deleting group-alpha when group-beta still exists patches the CRD instead of deleting the whole CRD
        del_res = await k8s.delete_rule_group_crd(
            namespace="monitoring",
            group_name="group-alpha",
            crd_name=None,
            dry_run=False,
        )
        assert del_res["action"] == "removed_group_from_crd"
        assert del_res["remaining_group_count"] == 1
        k8s._custom.delete_namespaced_custom_object.assert_not_called()

        # Deleting the last remaining group deletes the whole CRD
        single_group_crd = {
            **existing_crd,
            "spec": {"groups": [{"name": "group-beta", "rules": [{"alert": "BetaDown", "expr": "up == 0"}]}]},
        }
        k8s._custom.list_namespaced_custom_object.return_value = {"items": [single_group_crd]}
        del_last = await k8s.delete_rule_group_crd(
            namespace="monitoring",
            group_name="group-beta",
            crd_name=None,
            dry_run=False,
        )
        assert del_last["action"] == "deleted_crd"
        assert del_last["remaining_group_count"] == 0
        k8s._custom.delete_namespaced_custom_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_k8s_service_discovery_kubeconfig_and_crd_helpers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        monkeypatch.setenv("K8S_KUBECONFIG", "/tmp/custom-kubeconfig")
        with patch("prometheus_mcp_server.services.kubernetes_service.k8s_config") as mock_cfg, patch(
            "prometheus_mcp_server.services.kubernetes_service.k8s_client"
        ):
            k8s_init = KubernetesService(KubernetesConfig(enabled=True, context_name="prod-ctx"))
            k8s_init._ensure_initialized()
            mock_cfg.load_kube_config.assert_called_once_with(
                config_file="/tmp/custom-kubeconfig", context="prod-ctx"
            )

        k8s = KubernetesService(KubernetesConfig(enabled=True))
        k8s._initialized = True
        k8s._core = MagicMock()
        k8s._custom = MagicMock()

        fake_svc = SimpleNamespace(
            metadata=SimpleNamespace(
                name="checkout",
                namespace="prod",
                labels={"app.kubernetes.io/name": "checkout"},
            ),
            spec=SimpleNamespace(
                selector={"app": "checkout"},
                ports=[
                    SimpleNamespace(name="http", port=80, target_port=8080, protocol="TCP"),
                    SimpleNamespace(name="http-metrics", port=9090, target_port=9090, protocol="TCP"),
                ],
            ),
        )
        k8s._core.read_namespaced_service.return_value = fake_svc
        details = await k8s.discover_service_details("prod", "checkout")
        assert details is not None
        assert details["metrics_port"]["name"] == "http-metrics"

        # 404 returns None
        k8s._core.read_namespaced_service.side_effect = ApiException(status=404)
        assert await k8s.discover_service_details("prod", "missing") is None

        # Selector label discovery and CRD manifest helpers
        k8s._custom.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "spec": {
                        "serviceMonitorSelector": {"matchLabels": {"release": "prom-op"}},
                        "probeSelector": {"matchLabels": {"release": "prom-op"}},
                    }
                }
            ]
        }
        assert await k8s.get_servicemonitor_required_labels() == {"release": "prom-op"}
        assert await k8s.get_probe_required_labels() == {"release": "prom-op"}

        k8s._custom.get_namespaced_custom_object.return_value = {
            "kind": "ServiceMonitor",
            "metadata": {
                "name": "checkout-sm",
                "namespace": "monitoring",
                "managedFields": [{"manager": "kubectl"}],
            },
            "spec": {"endpoints": [{"port": "http-metrics", "bearerTokenSecret": {"key": "tok"}}]},
        }
        manifest = await k8s.get_crd_manifest("ServiceMonitor", "monitoring", "checkout-sm")
        assert manifest is not None
        assert "managedFields" not in manifest["metadata"]
        assert manifest["spec"]["endpoints"][0]["bearerTokenSecret"]["key"] == "***REDACTED***"


class TestPrometheusServiceFullApiAndUtils:
    @pytest.mark.asyncio
    @respx.mock
    async def test_ruler_api_service_metrics_config_and_tsdb(self) -> None:
        cfg = ServerConfig(
            backends=[
                BackendConfig(
                    id="default",
                    base_url="http://localhost:9090",
                    ruler_url="http://ruler:8080",
                    auth_header="Bearer tok-123",
                )
            ]
        )
        svc = PrometheusService(cfg)

        respx.get("http://localhost:9090/api/v1/targets/metadata").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        {"metric": "redis_up", "type": "gauge", "help": "Redis up", "unit": ""},
                        {"metric": "redis_up", "type": "gauge", "help": "Redis up", "unit": ""},
                    ],
                },
            )
        )
        respx.get("http://localhost:9090/api/v1/status/config").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "yaml": "global:\n  scrape_interval: 15s\n  evaluation_interval: 15s\n",
                    },
                },
            )
        )
        respx.get("http://localhost:9090/api/v1/status/tsdb").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "headStats": {"numSeries": 5000, "numLabelPairs": 800, "chunkCount": 10000},
                        "seriesCountByMetricName": [{"name": "redis_up", "value": 10}],
                    },
                },
            )
        )
        respx.get("http://localhost:9090/api/v1/status/walreplay").mock(
            return_value=httpx.Response(
                200,
                json={"status": "success", "data": {"min": 1, "max": 5, "current": 5}},
            )
        )
        respx.get("http://localhost:9090/api/v1/rules").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {"groups": [{"name": "g1", "file": "/etc/rules.yml", "rules": []}]},
                },
            )
        )
        respx.post("http://ruler:8080/api/v1/rules/prod").mock(
            return_value=httpx.Response(202)
        )
        respx.delete("http://ruler:8080/api/v1/rules/prod/g1").mock(
            return_value=httpx.Response(202)
        )

        sm = await svc.get_service_metrics("default", "redis")
        assert sm.total_count == 1
        assert sm.metrics[0].name == "redis_up"

        rcfg = await svc.get_config("default")
        assert rcfg.global_config["scrape_interval"] == "15s"

        card = await svc.get_cardinality_summary("default")
        assert card.overview.total_series == 5000

        wal = await svc.get_wal_replay("default")
        assert wal["current"] == 5

        grp = await svc.get_rule_group("default", "g1", file_filter="/etc/rules.yml")
        assert grp is not None and grp["name"] == "g1"

        up_res = await svc.upsert_ruler_group("default", "prod", "name: g1\nrules: []\n")
        assert up_res["status"] == "applied"
        del_res = await svc.delete_ruler_group("default", "prod", "g1")
        assert del_res["status"] == "deleted"
        await svc.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_endpoint_tester_and_promtool_runner(self) -> None:
        from unittest.mock import AsyncMock, patch
        from prometheus_mcp_server.utils.endpoint_tester import test_metrics_endpoint
        from prometheus_mcp_server.utils.promtool_runner import check_rules, test_rules

        respx.get("http://exporter.local:9100/metrics").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/plain; version=0.0.4"},
                text="# HELP up Target up\n# TYPE up gauge\nup{job=\"node\"} 1\n",
            )
        )
        ep = await test_metrics_endpoint("http://exporter.local:9100/metrics")
        assert ep["ok"] is True
        assert ep["format"] == "prometheus"
        assert "up" in ep["metrics_found"]

        with patch(
            "prometheus_mcp_server.utils.promtool_runner.is_promtool_available",
            return_value=True,
        ), patch(
            "prometheus_mcp_server.utils.promtool_runner.run_promtool_command",
            new=AsyncMock(return_value=(0, "SUCCESS: 2 rules found\n", "")),
        ):
            chk = await check_rules("groups: []")
            assert chk["valid"] is True
            assert chk["rules_checked"] == 2

            tst = await test_rules("groups: []", "tests: []")
            assert tst["passed"] is True
