"""Tests for CollectorConfigBuilder and ProvisionTools.

Tests the intent-driven collector provisioning system:
- Config generation from signals
- Processor ordering enforcement
- Exporter target auto-discovery
- Mode recommendation logic
- Resource sizing
- Spanmetrics wiring
- Filelog safety (self-exclusion, checkpoint storage)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Any, Dict, List

from opentelemetry_mcp_server.services.collector_config_builder import (
    CollectorConfigBuilder,
    _PROCESSOR_ORDER,
    _BACKEND_PATTERNS,
)


# ──────────────────────────────────────────────
# Test Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def mock_k8s():
    """Mock KubernetesService for builder tests."""
    svc = MagicMock()
    svc.is_available = True
    svc.list_otel_collectors = AsyncMock(return_value={"items": []})
    svc.list_services = AsyncMock(return_value=[])
    svc.list_deployments = AsyncMock(return_value=[])
    svc.list_namespaces = AsyncMock(return_value=["default", "monitoring"])
    svc.count_nodes = AsyncMock(return_value=3)
    return svc


@pytest.fixture
def builder(mock_k8s):
    """CollectorConfigBuilder with mocked K8s."""
    return CollectorConfigBuilder(mock_k8s)


# ──────────────────────────────────────────────
# Config Generation Tests
# ──────────────────────────────────────────────


class TestBuildConfig:
    """Test the main build_config method."""

    def test_basic_traces_metrics(self, builder):
        """Build config for traces + metrics with OTLP exporters."""
        config = builder.build_config(
            signals=["traces", "metrics"],
            exporter_targets={
                "traces": "jaeger:4317",
                "metrics": "prometheus:9090",
            },
        )

        assert "receivers" in config
        assert "processors" in config
        assert "exporters" in config
        assert "service" in config
        assert "extensions" in config

        # OTLP receiver always present
        assert "otlp" in config["receivers"]
        assert "grpc" in config["receivers"]["otlp"]["protocols"]
        assert "http" in config["receivers"]["otlp"]["protocols"]

        # Pipelines match requested signals
        pipelines = config["service"]["pipelines"]
        assert "traces" in pipelines
        assert "metrics" in pipelines
        assert "logs" not in pipelines

    def test_all_three_signals(self, builder):
        """Build config for all three signals."""
        config = builder.build_config(
            signals=["traces", "metrics", "logs"],
            exporter_targets={
                "traces": "tempo:4317",
                "metrics": "mimir:9009",
                "logs": "loki:3100",
            },
        )
        pipelines = config["service"]["pipelines"]
        assert len(pipelines) == 3
        assert set(pipelines.keys()) == {"traces", "metrics", "logs"}

    def test_single_signal_traces_only(self, builder):
        """Build config for traces only."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        pipelines = config["service"]["pipelines"]
        assert len(pipelines) == 1
        assert "traces" in pipelines

    def test_health_check_extension_always_present(self, builder):
        """health_check extension is always included."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        assert "health_check" in config["extensions"]
        assert config["extensions"]["health_check"]["endpoint"] == "0.0.0.0:13133"
        assert "health_check" in config["service"]["extensions"]


# ──────────────────────────────────────────────
# Processor Ordering Tests
# ──────────────────────────────────────────────


class TestProcessorOrdering:
    """Test best-practice processor chain enforcement."""

    def test_processor_order_is_correct(self, builder):
        """Processors must follow the recommended order."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        processor_names = list(config["processors"].keys())
        assert processor_names == _PROCESSOR_ORDER

    def test_processor_chain_in_all_pipelines(self, builder):
        """Every pipeline uses the same best-practice processor chain."""
        config = builder.build_config(
            signals=["traces", "metrics", "logs"],
            exporter_targets={
                "traces": "jaeger:4317",
                "metrics": "prometheus:9090",
                "logs": "loki:3100",
            },
        )
        for pname, pcfg in config["service"]["pipelines"].items():
            assert pcfg["processors"] == _PROCESSOR_ORDER, (
                f"Pipeline '{pname}' has wrong processor order"
            )

    def test_memory_limiter_is_first(self, builder):
        """memory_limiter must always be the first processor."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        processors = list(config["processors"].keys())
        assert processors[0] == "memory_limiter"

    def test_batch_is_last(self, builder):
        """batch must always be the last processor."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        processors = list(config["processors"].keys())
        assert processors[-1] == "batch"

    def test_k8sattributes_has_pod_association(self, builder):
        """k8sattributes must have pod_association for proper enrichment."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        k8s = config["processors"]["k8sattributes"]
        assert "pod_association" in k8s
        assert len(k8s["pod_association"]) >= 2

    def test_k8sattributes_extracts_essential_metadata(self, builder):
        """k8sattributes must extract essential K8s metadata."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        metadata = config["processors"]["k8sattributes"]["extract"]["metadata"]
        essential = [
            "k8s.namespace.name",
            "k8s.pod.name",
            "k8s.pod.uid",
            "k8s.deployment.name",
            "k8s.node.name",
        ]
        for attr in essential:
            assert attr in metadata, f"Missing essential attribute: {attr}"

    def test_resource_processor_sets_service_instance_id(self, builder):
        """resource processor must set service.instance.id from k8s.pod.uid."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        attrs = config["processors"]["resource"]["attributes"]
        assert any(
            a.get("key") == "service.instance.id"
            and a.get("from_attribute") == "k8s.pod.uid"
            for a in attrs
        )


# ──────────────────────────────────────────────
# Exporter Generation Tests
# ──────────────────────────────────────────────


class TestExporterGeneration:
    """Test exporter config generation from targets."""

    def test_otlp_grpc_exporter_for_jaeger(self, builder):
        """Jaeger endpoint should generate otlp gRPC exporter."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
        )
        assert "otlp/traces" in config["exporters"]
        exp = config["exporters"]["otlp/traces"]
        assert exp["endpoint"] == "jaeger:4317"
        assert exp["tls"]["insecure"] is True

    def test_prometheusremotewrite_exporter_for_prometheus(self, builder):
        """Prometheus endpoint should generate prometheusremotewrite exporter."""
        config = builder.build_config(
            signals=["metrics"],
            exporter_targets={"metrics": "prometheus:9090"},
        )
        assert "prometheusremotewrite/metrics" in config["exporters"]
        exp = config["exporters"]["prometheusremotewrite/metrics"]
        assert "/api/v1/write" in exp["endpoint"]

    def test_loki_exporter(self, builder):
        """Loki endpoint should generate otlphttp/loki exporter."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
        )
        assert "otlphttp/loki" in config["exporters"]

    def test_debug_exporter_fallback(self, builder):
        """__debug__ target should generate debug exporter."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "__debug__"},
        )
        assert "debug" in config["exporters"]
        pipeline = config["service"]["pipelines"]["traces"]
        assert "debug" in pipeline["exporters"]

    def test_opensearch_exporter(self, builder):
        """OpenSearch endpoint should generate opensearch exporter."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "opensearch:9200"},
        )
        assert "opensearch" in config["exporters"]

    def test_multiple_signals_different_exporters(self, builder):
        """Different signals can use different exporter types."""
        config = builder.build_config(
            signals=["traces", "metrics", "logs"],
            exporter_targets={
                "traces": "tempo:4317",
                "metrics": "prometheus:9090",
                "logs": "loki:3100",
            },
        )
        assert "otlp/traces" in config["exporters"]
        assert "prometheusremotewrite/metrics" in config["exporters"]
        assert "otlphttp/loki" in config["exporters"]



# ──────────────────────────────────────────────
# Exporter Path Suffix Tests
# ──────────────────────────────────────────────


class TestExporterPathSuffix:
    """Test well-known API path suffix auto-appending via _EXPORTER_DEFAULTS."""

    def test_loki_endpoint_has_otlp_path(self, builder):
        """Loki endpoint must include /otlp."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "http://loki.loki:3100"},
        )
        endpoint = config["exporters"]["otlphttp/loki"]["endpoint"]
        assert endpoint.endswith("/otlp")
        assert endpoint == "http://loki.loki:3100/otlp"

    def test_loki_endpoint_no_double_path(self, builder):
        """If endpoint already has the otlp path, don't double-append."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={
                "logs": "http://loki.loki:3100/otlp",
            },
        )
        endpoint = config["exporters"]["otlphttp/loki"]["endpoint"]
        assert endpoint == "http://loki.loki:3100/otlp"
        # Verify no double path
        assert endpoint.count("/otlp") == 1

    def test_loki_endpoint_trailing_slash_handled(self, builder):
        """Trailing slash on base endpoint should not cause double slash."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "http://loki:3100/"},
        )
        endpoint = config["exporters"]["otlphttp/loki"]["endpoint"]
        assert "//" not in endpoint.split("://", 1)[1]
        assert endpoint.endswith("/otlp")

    def test_loki_bare_endpoint_gets_scheme_and_path(self, builder):
        """Bare loki:3100 should get http:// scheme and otlp path."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
        )
        endpoint = config["exporters"]["otlphttp/loki"]["endpoint"]
        assert endpoint == "http://loki:3100/otlp"

    def test_prometheus_endpoint_has_write_path(self, builder):
        """Prometheus endpoint must include /api/v1/write."""
        config = builder.build_config(
            signals=["metrics"],
            exporter_targets={"metrics": "prometheus:9090"},
        )
        endpoint = config["exporters"]["prometheusremotewrite/metrics"]["endpoint"]
        assert endpoint.endswith("/api/v1/write")

    def test_prometheus_endpoint_no_double_path(self, builder):
        """If endpoint already has /api/v1/write, don't double-append."""
        config = builder.build_config(
            signals=["metrics"],
            exporter_targets={
                "metrics": "http://prometheus:9090/api/v1/write",
            },
        )
        endpoint = config["exporters"]["prometheusremotewrite/metrics"]["endpoint"]
        assert endpoint.count("/api/v1/write") == 1


# ──────────────────────────────────────────────
# Exporter Overrides Tests
# ──────────────────────────────────────────────


class TestExporterOverrides:
    """Test per-exporter config overrides (headers, TLS, auth)."""

    def test_loki_tenant_header_injected(self, builder):
        """exporter_overrides should inject X-Scope-OrgID header for Loki."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            exporter_overrides={
                "otlphttp/loki": {"headers": {"X-Scope-OrgID": "talkops"}},
            },
        )
        loki_cfg = config["exporters"]["otlphttp/loki"]
        assert "headers" in loki_cfg
        assert loki_cfg["headers"]["X-Scope-OrgID"] == "talkops"
        # Endpoint should still have the otlp path
        assert loki_cfg["endpoint"].endswith("/otlp")

    def test_overrides_deep_merge_preserves_existing(self, builder):
        """Overrides should merge, not replace, existing dict keys."""
        config = builder.build_config(
            signals=["metrics"],
            exporter_targets={"metrics": "prometheus:9090"},
            exporter_overrides={
                "prometheusremotewrite": {"tls": {"ca_file": "/etc/ssl/ca.pem"}},
            },
        )
        prom_cfg = config["exporters"]["prometheusremotewrite/metrics"]
        # Original tls.insecure should still be present
        assert prom_cfg["tls"]["insecure"] is True
        # New tls.ca_file should be merged in
        assert prom_cfg["tls"]["ca_file"] == "/etc/ssl/ca.pem"

    def test_overrides_add_new_keys(self, builder):
        """Overrides can add entirely new top-level keys."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            exporter_overrides={
                "otlphttp/loki": {"retry_on_failure": {"enabled": True}},
            },
        )
        loki_cfg = config["exporters"]["otlphttp/loki"]
        assert loki_cfg["retry_on_failure"]["enabled"] is True

    def test_overrides_for_unknown_exporter_ignored(self, builder):
        """Overrides for non-matching exporter types are silently ignored."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            exporter_overrides={
                "nonexistent": {"headers": {"X-Custom": "val"}},
            },
        )
        loki_cfg = config["exporters"]["otlphttp/loki"]
        assert "headers" not in loki_cfg

    def test_no_overrides_default(self, builder):
        """None overrides should produce same output as before."""
        config_without = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            exporter_overrides=None,
        )
        config_default = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
        )
        assert config_without["exporters"] == config_default["exporters"]

    def test_otlp_grpc_overrides(self, builder):
        """Overrides should work for default OTLP gRPC exporters too."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "tempo:4317"},
            exporter_overrides={
                "otlp": {"headers": {"Authorization": "Bearer token123"}},
            },
        )
        otlp_cfg = config["exporters"]["otlp/traces"]
        assert otlp_cfg["headers"]["Authorization"] == "Bearer token123"

    def test_elasticsearch_overrides(self, builder):
        """Overrides should work for Elasticsearch exporters."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "http://elastic-logs:9243"},
            exporter_overrides={
                "elasticsearch": {"user": "elastic", "password": "secret"},
            },
        )
        es_cfg = config["exporters"]["elasticsearch"]
        assert es_cfg["user"] == "elastic"
        assert es_cfg["password"] == "secret"

    def test_opensearch_overrides(self, builder):
        """Overrides should work for OpenSearch exporters."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "opensearch:9200"},
            exporter_overrides={
                "opensearch": {"logs_index": "custom-logs-index"},
            },
        )
        os_cfg = config["exporters"]["opensearch"]
        # Override should replace the default
        assert os_cfg["logs_index"] == "custom-logs-index"


# ──────────────────────────────────────────────
# Spanmetrics Tests
# ──────────────────────────────────────────────


class TestSpanmetrics:
    """Test spanmetrics connector generation."""

    def test_spanmetrics_connector_created(self, builder):
        """enable_spanmetrics should create a spanmetrics connector."""
        config = builder.build_config(
            signals=["traces", "metrics"],
            exporter_targets={
                "traces": "jaeger:4317",
                "metrics": "prometheus:9090",
            },
            enable_spanmetrics=True,
        )
        assert "connectors" in config
        assert "spanmetrics" in config["connectors"]

    def test_spanmetrics_wired_correctly(self, builder):
        """Spanmetrics: traces pipeline exports to spanmetrics,
        metrics pipeline receives from spanmetrics."""
        config = builder.build_config(
            signals=["traces", "metrics"],
            exporter_targets={
                "traces": "jaeger:4317",
                "metrics": "prometheus:9090",
            },
            enable_spanmetrics=True,
        )
        pipelines = config["service"]["pipelines"]

        # traces exports to spanmetrics
        assert "spanmetrics" in pipelines["traces"]["exporters"]

        # metrics receives from spanmetrics
        assert "spanmetrics" in pipelines["metrics"]["receivers"]

    def test_spanmetrics_has_default_dimensions(self, builder):
        """Spanmetrics should have sensible default dimensions."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
            enable_spanmetrics=True,
        )
        dims = config["connectors"]["spanmetrics"]["dimensions"]
        dim_names = [d["name"] for d in dims]
        assert "http.method" in dim_names
        assert "http.status_code" in dim_names

    def test_no_connectors_when_disabled(self, builder):
        """No connectors section when spanmetrics is disabled."""
        config = builder.build_config(
            signals=["traces"],
            exporter_targets={"traces": "jaeger:4317"},
            enable_spanmetrics=False,
        )
        assert "connectors" not in config


# ──────────────────────────────────────────────
# Filelog Tests
# ──────────────────────────────────────────────


class TestFilelog:
    """Test filelog receiver configuration."""

    def test_filelog_receiver_created(self, builder):
        """enable_filelog should add filelog receiver."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            enable_filelog=True,
            namespace="production",
            collector_name="prod-collector",
        )
        assert "filelog" in config["receivers"]

    def test_filelog_self_exclusion(self, builder):
        """Filelog must exclude its own collector's logs."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            enable_filelog=True,
            namespace="monitoring",
            collector_name="log-collector",
        )
        exclude = config["receivers"]["filelog"]["exclude"]
        assert any("log-collector" in e for e in exclude)

    def test_filelog_namespace_scoping(self, builder):
        """Filelog include path should be scoped to the target namespace."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            enable_filelog=True,
            namespace="production",
        )
        include = config["receivers"]["filelog"]["include"]
        assert any("production_" in i for i in include)

    def test_filelog_starts_at_end(self, builder):
        """Filelog should start_at=end in production (not beginning)."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            enable_filelog=True,
        )
        assert config["receivers"]["filelog"]["start_at"] == "end"

    def test_filelog_has_checkpoint_storage(self, builder):
        """Filelog should reference file_storage for checkpointing."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            enable_filelog=True,
        )
        assert config["receivers"]["filelog"]["storage"] == "file_storage"

    def test_filelog_in_pipeline(self, builder):
        """Filelog should be added to logs pipeline receivers."""
        config = builder.build_config(
            signals=["logs"],
            exporter_targets={"logs": "loki:3100"},
            enable_filelog=True,
        )
        pipeline = config["service"]["pipelines"]["logs"]
        assert "filelog" in pipeline["receivers"]
        assert "otlp" in pipeline["receivers"]  # OTLP still included


# ──────────────────────────────────────────────
# Mode Recommendation Tests
# ──────────────────────────────────────────────


class TestModeRecommendation:
    """Test deployment mode selection logic."""

    def test_deployment_for_traces_metrics(self):
        """traces + metrics should recommend deployment."""
        mode, _ = CollectorConfigBuilder.recommend_mode(["traces", "metrics"])
        assert mode == "deployment"

    def test_daemonset_for_filelog(self):
        """filelog should force daemonset."""
        mode, _ = CollectorConfigBuilder.recommend_mode(
            ["logs"], enable_filelog=True
        )
        assert mode == "daemonset"

    def test_statefulset_for_prometheus_scrape(self):
        """Prometheus scraping should recommend statefulset."""
        mode, _ = CollectorConfigBuilder.recommend_mode(
            ["metrics"], prometheus_scrape=True
        )
        assert mode == "statefulset"

    def test_deployment_for_otlp_logs(self):
        """OTLP logs (no filelog) should be deployment."""
        mode, _ = CollectorConfigBuilder.recommend_mode(["logs"])
        assert mode == "deployment"

    def test_rationale_is_not_empty(self):
        """Mode rationale must be non-empty."""
        _, rationale = CollectorConfigBuilder.recommend_mode(["traces"])
        assert len(rationale) > 10

    def test_filelog_overrides_prometheus(self):
        """filelog takes priority over prometheus_scrape."""
        mode, _ = CollectorConfigBuilder.recommend_mode(
            ["logs", "metrics"],
            enable_filelog=True,
            prometheus_scrape=True,
        )
        assert mode == "daemonset"


# ──────────────────────────────────────────────
# Resource Sizing Tests
# ──────────────────────────────────────────────


class TestResourceSizing:
    """Test K8s resource recommendation."""

    def test_small_cluster_sizing(self):
        resources = CollectorConfigBuilder.recommend_resources("small")
        assert resources["requests"]["cpu"] == "100m"
        assert resources["requests"]["memory"] == "256Mi"

    def test_medium_cluster_sizing(self):
        resources = CollectorConfigBuilder.recommend_resources("medium")
        assert resources["requests"]["cpu"] == "250m"

    def test_large_cluster_sizing(self):
        resources = CollectorConfigBuilder.recommend_resources("large")
        assert resources["requests"]["cpu"] == "500m"

    def test_unknown_cluster_defaults_to_medium(self):
        resources = CollectorConfigBuilder.recommend_resources("unknown")
        assert resources == CollectorConfigBuilder.recommend_resources("medium")


# ──────────────────────────────────────────────
# Cluster Size Detection Tests
# ──────────────────────────────────────────────


class TestClusterSizeDetection:
    """Test cluster size auto-detection."""

    @pytest.mark.asyncio
    async def test_small_cluster(self, mock_k8s):
        mock_k8s.count_nodes = AsyncMock(return_value=3)
        builder = CollectorConfigBuilder(mock_k8s)
        size, count = await builder.discover_cluster_size()
        assert size == "small"
        assert count == 3

    @pytest.mark.asyncio
    async def test_medium_cluster(self, mock_k8s):
        mock_k8s.count_nodes = AsyncMock(return_value=30)
        builder = CollectorConfigBuilder(mock_k8s)
        size, count = await builder.discover_cluster_size()
        assert size == "medium"

    @pytest.mark.asyncio
    async def test_large_cluster(self, mock_k8s):
        mock_k8s.count_nodes = AsyncMock(return_value=100)
        builder = CollectorConfigBuilder(mock_k8s)
        size, count = await builder.discover_cluster_size()
        assert size == "large"

    @pytest.mark.asyncio
    async def test_error_defaults_to_medium(self, mock_k8s):
        mock_k8s.count_nodes = AsyncMock(side_effect=Exception("conn refused"))
        builder = CollectorConfigBuilder(mock_k8s)
        size, count = await builder.discover_cluster_size()
        assert size == "medium"
        assert count == 0


# ──────────────────────────────────────────────
# Auto-Discovery Tests
# ──────────────────────────────────────────────


class TestAutoDiscovery:
    """Test exporter target auto-discovery."""

    @pytest.mark.asyncio
    async def test_discover_from_services(self, mock_k8s):
        """Should discover backends from K8s service names."""
        mock_k8s.list_services = AsyncMock(return_value=[
            {
                "name": "jaeger-collector",
                "namespace": "monitoring",
                "ports": [{"name": "grpc", "port": 4317, "target_port": 4317, "protocol": "TCP"}],
                "labels": {},
            },
            {
                "name": "prometheus-server",
                "namespace": "monitoring",
                "ports": [{"name": "http", "port": 9090, "target_port": 9090, "protocol": "TCP"}],
                "labels": {},
            },
        ])
        builder = CollectorConfigBuilder(mock_k8s)
        targets, meta = await builder.discover_exporter_targets(
            namespace="monitoring",
            signals=["traces", "metrics"],
        )
        assert "traces" in targets
        assert "jaeger" in targets["traces"]
        assert "metrics" in targets
        assert "prometheus" in targets["metrics"]

    @pytest.mark.asyncio
    async def test_discover_from_existing_collectors(self, mock_k8s):
        """Should discover backends from existing collector configs."""
        mock_k8s.list_otel_collectors = AsyncMock(return_value={
            "items": [{
                "metadata": {"name": "existing-collector", "namespace": "monitoring"},
                "spec": {
                    "config": {
                        "exporters": {
                            "otlp/traces": {"endpoint": "tempo:4317"},
                        },
                        "service": {
                            "pipelines": {
                                "traces": {
                                    "receivers": ["otlp"],
                                    "exporters": ["otlp/traces"],
                                },
                            },
                        },
                    },
                },
            }],
        })
        builder = CollectorConfigBuilder(mock_k8s)
        targets, meta = await builder.discover_exporter_targets(
            namespace="monitoring",
            signals=["traces"],
        )
        assert targets["traces"] == "tempo:4317"
        assert len(meta["existing_collectors"]) >= 1

    @pytest.mark.asyncio
    async def test_debug_fallback_when_nothing_found(self, mock_k8s):
        """Should fall back to debug exporter when no backends found."""
        builder = CollectorConfigBuilder(mock_k8s)
        targets, meta = await builder.discover_exporter_targets(
            namespace="empty-ns",
            signals=["traces"],
        )
        assert targets["traces"] == "__debug__"
        assert len(meta["fallbacks_used"]) == 1

    @pytest.mark.asyncio
    async def test_scans_well_known_namespaces(self, mock_k8s):
        """Should scan well-known observability namespaces."""
        builder = CollectorConfigBuilder(mock_k8s)
        _, meta = await builder.discover_exporter_targets(
            namespace="my-app",
            signals=["traces"],
        )
        scanned = meta["scanned_namespaces"]
        assert "my-app" in scanned
        assert "monitoring" in scanned
        assert "observability" in scanned

    @pytest.mark.asyncio
    async def test_custom_scan_namespaces(self, mock_k8s):
        """User-specified scan_namespaces should be used."""
        builder = CollectorConfigBuilder(mock_k8s)
        _, meta = await builder.discover_exporter_targets(
            namespace="my-app",
            signals=["traces"],
            scan_namespaces=["custom-ns-1", "custom-ns-2"],
        )
        scanned = meta["scanned_namespaces"]
        assert "custom-ns-1" in scanned
        assert "custom-ns-2" in scanned

    @pytest.mark.asyncio
    async def test_skips_debug_and_spanmetrics_exporters(self, mock_k8s):
        """Discovery should skip debug and spanmetrics exporters."""
        mock_k8s.list_otel_collectors = AsyncMock(return_value={
            "items": [{
                "metadata": {"name": "test", "namespace": "default"},
                "spec": {
                    "config": {
                        "exporters": {
                            "debug": {},
                            "spanmetrics": {},
                            "otlp/real": {"endpoint": "tempo:4317"},
                        },
                        "service": {
                            "pipelines": {
                                "traces": {
                                    "receivers": ["otlp"],
                                    "exporters": ["debug", "spanmetrics", "otlp/real"],
                                },
                            },
                        },
                    },
                },
            }],
        })
        builder = CollectorConfigBuilder(mock_k8s)
        targets, _ = await builder.discover_exporter_targets(
            namespace="default",
            signals=["traces"],
        )
        assert targets["traces"] == "tempo:4317"


# ──────────────────────────────────────────────
# Prometheus Scraping Tests
# ──────────────────────────────────────────────


class TestPrometheusScraping:
    """Test Prometheus receiver and Target Allocator generation."""

    def test_prometheus_receiver_created(self, builder):
        config = builder.build_config(
            signals=["metrics"],
            exporter_targets={"metrics": "prometheus:9090"},
            prometheus_scrape=True,
        )
        assert "prometheus" in config["receivers"]
        scrape_configs = config["receivers"]["prometheus"]["config"]["scrape_configs"]
        assert len(scrape_configs) >= 1

    def test_prometheus_in_metrics_pipeline(self, builder):
        config = builder.build_config(
            signals=["metrics"],
            exporter_targets={"metrics": "prometheus:9090"},
            prometheus_scrape=True,
        )
        pipeline = config["service"]["pipelines"]["metrics"]
        assert "prometheus" in pipeline["receivers"]


# ──────────────────────────────────────────────
# Backend Pattern Coverage Tests
# ──────────────────────────────────────────────


class TestBackendPatterns:
    """Verify all supported backend patterns."""

    def test_all_patterns_have_signal(self):
        for pattern, signal, _, _, _ in _BACKEND_PATTERNS:
            assert signal in ("traces", "metrics", "logs"), (
                f"Backend pattern '{pattern}' has invalid signal: {signal}"
            )

    def test_traces_backends_covered(self):
        traces_backends = [
            p for p, s, _, _, _ in _BACKEND_PATTERNS if s == "traces"
        ]
        assert "jaeger" in traces_backends
        assert "tempo" in traces_backends

    def test_metrics_backends_covered(self):
        metrics_backends = [
            p for p, s, _, _, _ in _BACKEND_PATTERNS if s == "metrics"
        ]
        assert "prometheus" in metrics_backends
        assert "mimir" in metrics_backends

    def test_logs_backends_covered(self):
        logs_backends = [
            p for p, s, _, _, _ in _BACKEND_PATTERNS if s == "logs"
        ]
        assert "opensearch" in logs_backends
        assert "loki" in logs_backends
        assert "elasticsearch" in logs_backends
