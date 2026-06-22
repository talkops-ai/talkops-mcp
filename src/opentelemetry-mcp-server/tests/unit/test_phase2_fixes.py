"""Unit tests for Phase 2 architectural gap fixes.

Tests:
  - Critique 1: Prometheus text parser + pipeline health report builder
  - Critique 2: Config snapshot compress/decompress + revert logic
  - Critique 3: Log transform OTTL generation + PII pattern registry
  - Critique 4: Multi-cluster context list + client pool
"""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ──────────────────────────────────────────────
# Critique 1: Collector Metrics Service
# ──────────────────────────────────────────────

SAMPLE_PROMETHEUS_TEXT = """\
# HELP otelcol_exporter_sent_spans Number of spans sent.
# TYPE otelcol_exporter_sent_spans counter
otelcol_exporter_sent_spans{exporter="otlp/jaeger"} 12345
otelcol_exporter_sent_spans{exporter="otlp/tempo"} 678
# HELP otelcol_exporter_send_failed_spans Number of spans failed.
# TYPE otelcol_exporter_send_failed_spans counter
otelcol_exporter_send_failed_spans{exporter="otlp/jaeger"} 0
otelcol_exporter_send_failed_spans{exporter="otlp/tempo"} 42
# HELP otelcol_receiver_accepted_spans Number of spans accepted.
# TYPE otelcol_receiver_accepted_spans counter
otelcol_receiver_accepted_spans{receiver="otlp",transport="grpc"} 13023
# HELP otelcol_receiver_refused_spans Number of spans refused.
# TYPE otelcol_receiver_refused_spans counter
otelcol_receiver_refused_spans{receiver="otlp",transport="grpc"} 5
# HELP otelcol_exporter_queue_size Current queue size.
# TYPE otelcol_exporter_queue_size gauge
otelcol_exporter_queue_size{exporter="otlp/jaeger"} 10
# HELP otelcol_exporter_queue_capacity Queue capacity.
# TYPE otelcol_exporter_queue_capacity gauge
otelcol_exporter_queue_capacity{exporter="otlp/jaeger"} 1000
# HELP otelcol_processor_dropped_spans Processor dropped spans.
# TYPE otelcol_processor_dropped_spans counter
otelcol_processor_dropped_spans{processor="tail_sampling"} 3
# some random unrelated metric
http_requests_total{method="GET"} 999
"""


class TestPrometheusParser:
    """Test the Prometheus text format parser."""

    def test_parses_pipeline_metrics(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text,
        )

        samples = parse_prometheus_text(SAMPLE_PROMETHEUS_TEXT)

        # Should only parse otelcol_* metrics, skip http_requests_total
        names = {s.name for s in samples}
        assert "http_requests_total" not in names
        assert "otelcol_exporter_sent_spans" in names
        assert "otelcol_receiver_accepted_spans" in names
        assert "otelcol_processor_dropped_spans" in names

    def test_parses_labels_correctly(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text,
        )

        samples = parse_prometheus_text(SAMPLE_PROMETHEUS_TEXT)
        jaeger_sent = [
            s for s in samples
            if s.name == "otelcol_exporter_sent_spans"
            and s.labels.get("exporter") == "otlp/jaeger"
        ]
        assert len(jaeger_sent) == 1
        assert jaeger_sent[0].value == 12345.0

    def test_parses_multi_label_metrics(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text,
        )

        samples = parse_prometheus_text(SAMPLE_PROMETHEUS_TEXT)
        recv = [
            s for s in samples
            if s.name == "otelcol_receiver_accepted_spans"
        ]
        assert len(recv) == 1
        assert recv[0].labels == {"receiver": "otlp", "transport": "grpc"}

    def test_skips_comments_and_blank_lines(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text,
        )

        text = "# HELP foo\n# TYPE foo counter\n\n\notelcol_exporter_sent_spans{exporter=\"x\"} 1\n"
        samples = parse_prometheus_text(text)
        assert len(samples) == 1

    def test_handles_empty_input(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text,
        )

        assert parse_prometheus_text("") == []
        assert parse_prometheus_text("# just comments\n") == []


class TestHealthReportBuilder:
    """Test the pipeline health report builder."""

    def test_healthy_pipeline(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text, build_health_report,
        )

        # No failures — pipeline is healthy
        text = """\
otelcol_exporter_sent_spans{exporter="otlp"} 100
otelcol_exporter_send_failed_spans{exporter="otlp"} 0
otelcol_receiver_accepted_spans{receiver="otlp",transport="grpc"} 100
"""
        samples = parse_prometheus_text(text)
        report = build_health_report(samples, "test", "ns", "http://test:8888/metrics")

        assert report.healthy is True
        assert len(report.warnings) == 0
        assert "otlp" in report.exporters

    def test_unhealthy_pipeline_with_failures(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text, build_health_report,
        )

        samples = parse_prometheus_text(SAMPLE_PROMETHEUS_TEXT)
        report = build_health_report(samples, "test", "ns", "http://test:8888/metrics")

        # otlp/tempo has 42 failed sends
        assert report.healthy is False
        assert any("otlp/tempo" in w for w in report.warnings)

    def test_queue_saturation_warning(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text, build_health_report,
        )

        text = """\
otelcol_exporter_queue_size{exporter="x"} 900
otelcol_exporter_queue_capacity{exporter="x"} 1000
"""
        samples = parse_prometheus_text(text)
        report = build_health_report(samples, "test", "ns", "http://test:8888/metrics")

        assert report.healthy is False
        assert any("90.0%" in w for w in report.warnings)
        assert report.queue_health["x"]["utilization_pct"] == 90.0

    def test_processor_drop_warning(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text, build_health_report,
        )

        text = "otelcol_processor_dropped_spans{processor=\"batch\"} 15\n"
        samples = parse_prometheus_text(text)
        report = build_health_report(samples, "test", "ns", "http://test:8888/metrics")

        assert "batch" in report.processors
        assert report.processors["batch"]["dropped"]["spans"] == 15.0
        assert any("batch" in w for w in report.warnings)

    def test_receiver_refused_warning(self):
        from opentelemetry_mcp_server.services.collector_metrics_service import (
            parse_prometheus_text, build_health_report,
        )

        text = 'otelcol_receiver_refused_spans{receiver="otlp",transport="grpc"} 10\n'
        samples = parse_prometheus_text(text)
        report = build_health_report(samples, "test", "ns", "http://test:8888/metrics")

        assert any("otlp/grpc" in w for w in report.warnings)


# ──────────────────────────────────────────────
# Critique 2: Config Snapshot & Rollback
# ──────────────────────────────────────────────

class TestConfigSnapshot:
    """Test compress/decompress round-trip and snapshot storage."""

    def test_compress_decompress_round_trip(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        original = "receivers:\n  otlp:\n    protocols:\n      grpc:\n"
        compressed = KubernetesService._compress_config(original)

        # Should be base64 string
        assert isinstance(compressed, str)
        assert len(compressed) < len(original) * 2  # Not absurdly large

        decompressed = KubernetesService._decompress_config(compressed)
        assert decompressed == original

    def test_compress_large_config(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        # Simulate a realistic large config
        config = "key: value\n" * 500
        compressed = KubernetesService._compress_config(config)
        decompressed = KubernetesService._decompress_config(compressed)
        assert decompressed == config

    def test_store_config_snapshot_adds_annotations(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)

        existing_crd = {
            "spec": {"config": "old_config_yaml"},
            "metadata": {"name": "test"},
        }
        new_body: dict[str, Any] = {
            "metadata": {"name": "test"},
            "spec": {"config": "new_config_yaml"},
        }

        svc._store_config_snapshot(existing_crd, new_body)

        annotations = new_body["metadata"]["annotations"]
        assert KubernetesService._SNAPSHOT_ANNOTATION in annotations
        assert KubernetesService._SNAPSHOT_TIMESTAMP_ANNOTATION in annotations

        # Verify the snapshot decompresses to the OLD config
        restored = KubernetesService._decompress_config(
            annotations[KubernetesService._SNAPSHOT_ANNOTATION]
        )
        assert restored == "old_config_yaml"

    def test_store_config_snapshot_handles_dict_config(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)

        existing_crd = {
            "spec": {"config": {"receivers": {"otlp": {}}}},
            "metadata": {"name": "test"},
        }
        new_body: dict[str, Any] = {"metadata": {"name": "test"}, "spec": {}}

        svc._store_config_snapshot(existing_crd, new_body)

        annotations = new_body["metadata"]["annotations"]
        restored = KubernetesService._decompress_config(
            annotations[KubernetesService._SNAPSHOT_ANNOTATION]
        )
        assert json.loads(restored) == {"receivers": {"otlp": {}}}

    def test_store_config_snapshot_skips_empty_config(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)

        existing_crd = {"spec": {"config": ""}, "metadata": {}}
        new_body: dict[str, Any] = {"metadata": {}, "spec": {}}

        svc._store_config_snapshot(existing_crd, new_body)

        # Should not add annotations
        assert "annotations" not in new_body.get("metadata", {})


class TestRevertCollectorConfig:
    """Test the revert_collector_config method."""

    @pytest.mark.asyncio
    async def test_revert_dry_run_with_snapshot(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)
        svc._initialized = True
        svc._k8s_config = MagicMock(enabled=True)

        compressed = KubernetesService._compress_config("old_config")

        svc.get_otel_collector = AsyncMock(return_value={
            "metadata": {
                "annotations": {
                    KubernetesService._SNAPSHOT_ANNOTATION: compressed,
                    KubernetesService._SNAPSHOT_TIMESTAMP_ANNOTATION: "2025-01-01T00:00:00Z",
                }
            },
            "spec": {"config": "new_config"},
        })

        result = await svc.revert_collector_config("ns", "test", dry_run=True)

        assert result["action"] == "dry_run"
        assert result["snapshot_timestamp"] == "2025-01-01T00:00:00Z"
        assert "old_config" in result["snapshot_config_preview"]
        assert "new_config" in result["current_config_preview"]

    @pytest.mark.asyncio
    async def test_revert_no_snapshot(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)
        svc._initialized = True
        svc._k8s_config = MagicMock(enabled=True)

        svc.get_otel_collector = AsyncMock(return_value={
            "metadata": {"annotations": {}},
            "spec": {"config": "some_config"},
        })

        result = await svc.revert_collector_config("ns", "test", dry_run=True)
        assert result["action"] == "no_snapshot"

    @pytest.mark.asyncio
    async def test_revert_apply(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)
        svc._initialized = True
        svc._k8s_config = MagicMock(enabled=True)

        compressed = KubernetesService._compress_config("original_good_config")

        svc.get_otel_collector = AsyncMock(return_value={
            "metadata": {
                "annotations": {
                    KubernetesService._SNAPSHOT_ANNOTATION: compressed,
                    KubernetesService._SNAPSHOT_TIMESTAMP_ANNOTATION: "2025-01-01T00:00:00Z",
                }
            },
            "spec": {"config": "broken_config", "mode": "deployment"},
        })
        svc.create_or_patch_collector = AsyncMock(return_value={})

        result = await svc.revert_collector_config("ns", "test", dry_run=False)

        assert result["action"] == "reverted"
        svc.create_or_patch_collector.assert_called_once()
        call_kwargs = svc.create_or_patch_collector.call_args[1]
        assert call_kwargs["spec"]["config"] == "original_good_config"


# ──────────────────────────────────────────────
# Critique 3: Log Transform & PII Masking
# ──────────────────────────────────────────────

class TestLogTransformGeneration:
    """Test OTTL log transform config generation."""

    def test_json_parsing_only(self):
        from opentelemetry_mcp_server.tools.logs.log_transform_tools import (
            generate_log_transform_config,
        )

        config = generate_log_transform_config(parse_json=True)

        assert "processors" in config
        proc = config["processors"]["transform/log_processing"]
        assert proc["error_mode"] == "ignore"

        statements = proc["log_statements"][0]["statements"]
        assert any("ParseJSON" in s for s in statements)
        assert proc["log_statements"][0]["context"] == "log"

    def test_pii_masking_only(self):
        from opentelemetry_mcp_server.tools.logs.log_transform_tools import (
            generate_log_transform_config,
        )

        config = generate_log_transform_config(
            parse_json=False, mask_patterns=["email", "ssn"]
        )

        proc = config["processors"]["transform/log_processing"]
        statements = proc["log_statements"][0]["statements"]

        # Should have masking statements
        assert any("REDACTED_EMAIL" in s for s in statements)
        assert any("***-**-****" in s for s in statements)

        # Should NOT have JSON parsing
        assert not any("ParseJSON" in s for s in statements)

    def test_combined_json_and_pii(self):
        from opentelemetry_mcp_server.tools.logs.log_transform_tools import (
            generate_log_transform_config,
        )

        config = generate_log_transform_config(
            parse_json=True,
            mask_patterns=["credit_card"],
            extract_fields=["user_id", "request_id"],
        )

        proc = config["processors"]["transform/log_processing"]
        statements = proc["log_statements"][0]["statements"]

        # JSON parsing
        assert any("ParseJSON" in s for s in statements)
        # Field extraction
        assert any("user_id" in s for s in statements)
        assert any("request_id" in s for s in statements)
        # PII masking
        assert any("****-****-****-****" in s for s in statements)

    def test_empty_input_returns_empty(self):
        from opentelemetry_mcp_server.tools.logs.log_transform_tools import (
            generate_log_transform_config,
        )

        config = generate_log_transform_config(
            parse_json=False, mask_patterns=None
        )
        assert config == {}

    def test_custom_mask_rules(self):
        from opentelemetry_mcp_server.tools.logs.log_transform_tools import (
            generate_log_transform_config,
        )

        config = generate_log_transform_config(
            parse_json=False,
            custom_mask_rules=[
                {
                    "field": "body",
                    "regex": r"secret_key=\\w+",
                    "replacement": "secret_key=[HIDDEN]",
                },
                {
                    "field": "api_key",
                    "regex": r".*",
                    "replacement": "[REDACTED]",
                },
            ],
        )

        proc = config["processors"]["transform/log_processing"]
        statements = proc["log_statements"][0]["statements"]

        assert any("secret_key=[HIDDEN]" in s for s in statements)
        assert any("api_key" in s for s in statements)

    def test_all_pii_patterns_valid(self):
        from opentelemetry_mcp_server.tools.logs.log_transform_tools import (
            _PII_PATTERNS,
        )

        for name, info in _PII_PATTERNS.items():
            assert "description" in info, f"Pattern {name} missing description"
            assert "regex" in info, f"Pattern {name} missing regex"
            assert "replacement" in info, f"Pattern {name} missing replacement"
            assert len(info["regex"]) > 0, f"Pattern {name} has empty regex"

    def test_unknown_pattern_not_in_output(self):
        from opentelemetry_mcp_server.tools.logs.log_transform_tools import (
            generate_log_transform_config,
        )

        config = generate_log_transform_config(
            parse_json=False,
            mask_patterns=["nonexistent_pattern"],
        )
        # Unknown patterns are silently skipped
        assert config == {}


# ──────────────────────────────────────────────
# Critique 4: Multi-Cluster Context
# ──────────────────────────────────────────────

class TestMultiClusterContext:
    """Test multi-cluster context support."""

    @pytest.mark.asyncio
    async def test_list_available_contexts(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = MagicMock()

        mock_contexts = [
            {"name": "prod-us-east", "context": {"cluster": "prod", "user": "admin", "namespace": "default"}},
            {"name": "staging", "context": {"cluster": "staging", "user": "dev", "namespace": "otel-demo"}},
        ]
        mock_current = {"name": "prod-us-east"}

        with patch(
            "opentelemetry_mcp_server.services.kubernetes_service.KubernetesService.list_available_contexts"
        ) as mock_list:
            # Actually test the real method instead
            pass

        # Test by mocking the kubernetes library
        with patch(
            "kubernetes.config.list_kube_config_contexts",
            return_value=(mock_contexts, mock_current),
        ):
            result = await svc.list_available_contexts()

        assert len(result) == 2
        assert result[0]["name"] == "prod-us-east"
        assert result[0]["is_current"] is True
        assert result[1]["name"] == "staging"
        assert result[1]["is_current"] is False
        assert result[1]["namespace"] == "otel-demo"

    def test_client_pool_caches_default(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )
        from opentelemetry_mcp_server.config import KubernetesConfig

        with patch("kubernetes.config.load_kube_config"):
            with patch("kubernetes.client.CoreV1Api") as mock_core:
                with patch("kubernetes.client.AppsV1Api") as mock_apps:
                    with patch("kubernetes.client.CustomObjectsApi") as mock_custom:
                        svc = KubernetesService(
                            k8s_config=KubernetesConfig(
                                enabled=True
                            )
                        )

        # Default context should be cached in pool
        assert None in svc._client_pool
        assert svc._initialized is True



    @pytest.mark.asyncio
    async def test_list_contexts_error_fallback(self):
        from opentelemetry_mcp_server.services.kubernetes_service import (
            KubernetesService,
        )

        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = MagicMock()

        with patch(
            "kubernetes.config.list_kube_config_contexts",
            side_effect=Exception("no kubeconfig"),
        ):
            result = await svc.list_available_contexts()

        # Should return fallback with error
        assert len(result) == 1
        assert result[0]["is_current"] is True
        assert "error" in result[0]
