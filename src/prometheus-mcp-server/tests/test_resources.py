"""Tests for MCP resource modules."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from prometheus_mcp_server.resources.backend_resources import BackendResources
from prometheus_mcp_server.resources.config_resources import ConfigResources
from prometheus_mcp_server.resources.topology_resources import TopologyResources
from prometheus_mcp_server.resources.metadata_resources import MetadataResources
from prometheus_mcp_server.resources.tsdb_resources import TsdbResources
from prometheus_mcp_server.resources.static_resources import StaticResources
from prometheus_mcp_server.resources.rules_resources import RulesResources
from prometheus_mcp_server.resources.exporter_resources import ExporterResources
from prometheus_mcp_server.resources.kubernetes_resources import KubernetesResources
from prometheus_mcp_server.models.backend import BackendInfo, BackendCapabilities
from prometheus_mcp_server.models.metadata import RuntimeConfig, MetricCatalog, MetricMetadata, CardinalitySummary, CardinalityOverview
from prometheus_mcp_server.models.target import ServiceTopology, ServiceInfo, FailedTargetsSummary, FailedTarget, ServiceMetricsList


def _make_service_locator(prometheus_service=None):
    return {
        "prometheus_service": prometheus_service or MagicMock(),
        "kubernetes_service": MagicMock(),
        "config": MagicMock(),
    }


def _register_resources(resource_cls, prom_svc):
    sl = _make_service_locator(prometheus_service=prom_svc)
    resource = resource_cls(sl)
    mcp = MagicMock()
    registered = {}

    def capture_resource(uri, **kwargs):
        def decorator(fn):
            registered[uri] = fn
            return fn
        return decorator

    mcp.resource = capture_resource
    resource.register(mcp)
    return registered


class TestBackendResources:
    def setup_method(self):
        self.prom_svc = MagicMock()
        self.prom_svc.list_backends.return_value = [
            BackendInfo(id="test", base_url="http://localhost:9090"),
        ]
        self.prom_svc.check_health = AsyncMock(return_value="healthy")
        self.prom_svc.get_backend_capabilities = AsyncMock(
            return_value=BackendCapabilities(
                backend=BackendInfo(id="test", base_url="http://localhost:9090"),
            )
        )
        self.registered = _register_resources(BackendResources, self.prom_svc)

    @pytest.mark.asyncio
    async def test_list_backends_resource(self):
        result = await self.registered["prom://system/backends"]()
        data = json.loads(result)
        assert "backends" in data
        assert len(data["backends"]) == 1

    @pytest.mark.asyncio
    async def test_get_backend_resource(self):
        result = await self.registered["prom://system/backends/{backend_id}"](backend_id="test")
        data = json.loads(result)
        assert data["backend"]["id"] == "test"


class TestConfigResources:
    def setup_method(self):
        self.prom_svc = MagicMock()
        self.prom_svc.list_backends.return_value = [
            BackendInfo(id="test", base_url="http://localhost:9090"),
        ]
        self.prom_svc.get_config = AsyncMock(
            return_value=RuntimeConfig(global_config={"scrape_interval": "30s"})
        )
        self.registered = _register_resources(ConfigResources, self.prom_svc)

    @pytest.mark.asyncio
    async def test_runtime_config_resource(self):
        result = await self.registered["prom://config/runtime"]()
        data = json.loads(result)
        assert "test" in data
        assert data["test"]["global_config"]["scrape_interval"] == "30s"


class TestTopologyResources:
    def setup_method(self):
        self.prom_svc = MagicMock()
        self.prom_svc.list_backends.return_value = [
            BackendInfo(id="test", base_url="http://localhost:9090"),
        ]
        self.prom_svc.get_service_topology = AsyncMock(
            return_value=ServiceTopology(services=[
                ServiceInfo(service_id="test/prometheus", backend_id="test", job="prometheus"),
            ])
        )
        self.prom_svc.get_failed_targets = AsyncMock(
            return_value=FailedTargetsSummary(failed_targets=[
                FailedTarget(backend_id="test", job="myapp", instance="pod1:8080"),
            ])
        )
        self.prom_svc.get_service_metrics = AsyncMock(
            return_value=ServiceMetricsList(
                job="traefik-metrics",
                backend_id="test",
                metrics=[
                    MetricMetadata(name="traefik_service_requests_total", type="counter",
                                   help="Total HTTP requests by service"),
                    MetricMetadata(name="traefik_open_connections", type="gauge",
                                   help="Current open connections"),
                ],
                total_count=2,
            )
        )
        self.registered = _register_resources(TopologyResources, self.prom_svc)

    @pytest.mark.asyncio
    async def test_services_resource(self):
        result = await self.registered["prom://topology/services"]()
        data = json.loads(result)
        assert len(data["services"]) == 1

    @pytest.mark.asyncio
    async def test_failed_targets_resource(self):
        result = await self.registered["prom://topology/failed_targets"]()
        data = json.loads(result)
        assert len(data["failed_targets"]) == 1

    @pytest.mark.asyncio
    async def test_service_metrics_resource(self):
        result = await self.registered["prom://topology/services/{job}/metrics"](job="traefik-metrics")
        data = json.loads(result)
        assert data["job"] == "traefik-metrics"
        assert data["total_count"] == 2
        assert len(data["metrics"]) == 2
        metric_names = [m["name"] for m in data["metrics"]]
        assert "traefik_service_requests_total" in metric_names
        assert "traefik_open_connections" in metric_names


class TestMetadataResources:
    def setup_method(self):
        self.prom_svc = MagicMock()
        self.prom_svc.list_backends.return_value = [
            BackendInfo(id="test", base_url="http://localhost:9090"),
        ]
        self.prom_svc.get_metric_catalog = AsyncMock(
            return_value=MetricCatalog(
                metrics=[MetricMetadata(name="up", type="gauge")],
                total_count=1,
            )
        )
        self.registered = _register_resources(MetadataResources, self.prom_svc)

    @pytest.mark.asyncio
    async def test_metric_catalog_resource(self):
        result = await self.registered["prom://metadata/catalog"]()
        data = json.loads(result)
        assert "test" in data
        assert data["test"]["total_count"] == 1


class TestTsdbResources:
    def setup_method(self):
        self.prom_svc = MagicMock()
        self.prom_svc.list_backends.return_value = [
            BackendInfo(id="test", base_url="http://localhost:9090"),
        ]
        self.prom_svc.get_cardinality_summary = AsyncMock(
            return_value=CardinalitySummary(
                overview=CardinalityOverview(total_series=50000),
            )
        )
        self.registered = _register_resources(TsdbResources, self.prom_svc)

    @pytest.mark.asyncio
    async def test_cardinality_resource(self):
        result = await self.registered["prom://tsdb/cardinality"]()
        data = json.loads(result)
        assert data["test"]["overview"]["total_series"] == 50000


class TestStaticResources:
    def setup_method(self):
        self.registered = _register_resources(StaticResources, MagicMock())

    @pytest.mark.asyncio
    async def test_best_practices_resource(self):
        result = await self.registered["prom://best-practices"]()
        assert "Counter Rule" in result or "Best Practices" in result

    @pytest.mark.asyncio
    async def test_onboarding_guide_resource(self):
        result = await self.registered["prom://onboarding-guide"]()
        assert "Onboarding" in result


class TestRulesResources:
    """Tests for prom://rules/groups — replaces the retired prom_list_rule_groups tool."""

    def setup_method(self):
        self.prom_svc = MagicMock()
        self.prom_svc.list_backends.return_value = [
            BackendInfo(id="test", base_url="http://localhost:9090"),
        ]
        self.prom_svc.list_rule_groups = AsyncMock(return_value={
            "groups": [
                {"name": "alerts", "rules": [
                    {"alert": "HighCPU", "expr": "cpu > 90"},
                    {"record": "job:cpu:avg", "expr": "avg(cpu)"},
                ]},
            ]
        })
        self.registered = _register_resources(RulesResources, self.prom_svc)

    @pytest.mark.asyncio
    async def test_rule_groups_resource(self):
        result = await self.registered["prom://rules/groups"]()
        data = json.loads(result)
        assert "test" in data
        assert data["test"]["total_groups"] == 1
        assert data["test"]["total_alert_rules"] == 1
        assert data["test"]["total_recording_rules"] == 1


class TestExporterResources:
    """Tests for prom://exporters/catalog — replaces the retired prom_list_exporters tool."""

    def setup_method(self):
        self.registered = _register_resources(ExporterResources, MagicMock())

    @pytest.mark.asyncio
    async def test_exporter_catalog_resource(self):
        result = await self.registered["prom://exporters/catalog"]()
        data = json.loads(result)
        assert "exporters" in data
        assert "total_count" in data
        assert data["total_count"] >= 7
        # Verify each exporter has expected fields
        for exporter in data["exporters"]:
            assert "name" in exporter
            assert "description" in exporter
            assert "default_ports" in exporter
            assert "image" in exporter


def _register_resources_with_k8s(resource_cls, prom_svc, k8s_svc):
    """Register resources with both prometheus and kubernetes services injected."""
    sl = _make_service_locator(prometheus_service=prom_svc)
    sl["kubernetes_service"] = k8s_svc
    resource = resource_cls(sl)
    mcp = MagicMock()
    registered = {}

    def capture_resource(uri, **kwargs):
        def decorator(fn):
            registered[uri] = fn
            return fn
        return decorator

    mcp.resource = capture_resource
    resource.register(mcp)
    return registered


class TestKubernetesResources:
    """Tests for prom://kubernetes/prometheusrules — exposes PrometheusRule CRD metadata."""

    def setup_method(self):
        self.k8s_svc = MagicMock()
        self.k8s_svc.list_prometheus_rules = AsyncMock(return_value={
            "items": [
                {
                    "metadata": {
                        "name": "kube-prometheus-stack-alertmanager.rules",
                        "namespace": "monitoring",
                        "labels": {
                            "release": "kube-prometheus-stack",
                            "app": "kube-prometheus-stack",
                        },
                        "annotations": {},
                    },
                    "spec": {
                        "groups": [
                            {
                                "name": "alertmanager.rules",
                                "interval": "30s",
                                "rules": [
                                    {"alert": "AlertmanagerDown", "expr": "up == 0"},
                                    {"alert": "AlertmanagerClusterCrashlooping", "expr": "rate(x[5m]) > 0"},
                                ],
                            },
                        ],
                    },
                },
                {
                    "metadata": {
                        "name": "custom-recording-rules",
                        "namespace": "default",
                        "labels": {
                            "release": "kube-prometheus-stack",
                        },
                        "annotations": {
                            "description": "Custom recording rules",
                        },
                    },
                    "spec": {
                        "groups": [
                            {
                                "name": "recording.rules",
                                "rules": [
                                    {"record": "job:http_requests:rate5m", "expr": "rate(http_requests_total[5m])"},
                                ],
                            },
                            {
                                "name": "mixed.rules",
                                "rules": [
                                    {"alert": "HighErrorRate", "expr": "rate(errors[5m]) > 0.05"},
                                    {"record": "job:errors:rate5m", "expr": "rate(errors_total[5m])"},
                                ],
                            },
                        ],
                    },
                },
            ],
        })
        self.registered = _register_resources_with_k8s(
            KubernetesResources, MagicMock(), self.k8s_svc
        )

    @pytest.mark.asyncio
    async def test_prometheus_rules_resource(self):
        result = await self.registered["prom://kubernetes/prometheusrules"]()
        data = json.loads(result)

        assert data["total_crds"] == 2
        assert data["total_groups"] == 3
        assert data["total_alert_rules"] == 3
        assert data["total_recording_rules"] == 2

        # Verify first CRD
        first = data["prometheus_rules"][0]
        assert first["name"] == "kube-prometheus-stack-alertmanager.rules"
        assert first["namespace"] == "monitoring"
        assert first["labels"]["release"] == "kube-prometheus-stack"
        assert first["total_groups"] == 1
        assert first["total_alert_rules"] == 2
        assert first["total_recording_rules"] == 0

        # Verify group summaries
        group = first["groups"][0]
        assert group["name"] == "alertmanager.rules"
        assert group["interval"] == "30s"
        assert group["alert_rules"] == 2
        assert group["recording_rules"] == 0
        assert group["total_rules"] == 2

        # Verify second CRD with mixed rules
        second = data["prometheus_rules"][1]
        assert second["name"] == "custom-recording-rules"
        assert second["namespace"] == "default"
        assert second["total_groups"] == 2
        assert second["total_alert_rules"] == 1
        assert second["total_recording_rules"] == 2

    @pytest.mark.asyncio
    async def test_prometheus_rules_resource_no_k8s(self):
        """When kubernetes_service is None, return a helpful error."""
        sl = _make_service_locator(prometheus_service=MagicMock())
        sl["kubernetes_service"] = None
        resource = KubernetesResources(sl)
        mcp = MagicMock()
        registered = {}

        def capture_resource(uri, **kwargs):
            def decorator(fn):
                registered[uri] = fn
                return fn
            return decorator

        mcp.resource = capture_resource
        resource.register(mcp)

        result = await registered["prom://kubernetes/prometheusrules"]()
        data = json.loads(result)
        assert "error" in data
        assert "K8S_ENABLED" in data["hint"]

    @pytest.mark.asyncio
    async def test_prometheus_rules_resource_empty_cluster(self):
        """When no PrometheusRules exist, return empty results."""
        self.k8s_svc.list_prometheus_rules = AsyncMock(return_value={"items": []})
        self.registered = _register_resources_with_k8s(
            KubernetesResources, MagicMock(), self.k8s_svc
        )
        result = await self.registered["prom://kubernetes/prometheusrules"]()
        data = json.loads(result)

        assert data["total_crds"] == 0
        assert data["total_groups"] == 0
        assert data["prometheus_rules"] == []
