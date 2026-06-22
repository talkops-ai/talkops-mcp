"""Tests for CollectorConfigService.

These tests exercise the pure logic service with sample YAML configs
and no Kubernetes API interaction.
"""

import pytest

from opentelemetry_mcp_server.exceptions import OtelConfigParseError
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)


class TestParseCollectorConfig:
    """Test config parsing."""

    def test_parse_yaml_string(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        assert "receivers" in cfg
        assert "processors" in cfg
        assert "exporters" in cfg
        assert "service" in cfg

    def test_parse_dict_config(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cr = sample_collector_cr.copy()
        cr["spec"]["config"] = {"receivers": {"otlp": {}}, "service": {"pipelines": {}}}
        cfg = collector_config_service.parse_collector_config(cr)
        assert "receivers" in cfg

    def test_missing_config_raises(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        cr = {"spec": {}}
        with pytest.raises(OtelConfigParseError):
            collector_config_service.parse_collector_config(cr)

    def test_invalid_yaml_raises(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        cr = {"spec": {"config": ": invalid: yaml: {"}}
        with pytest.raises(OtelConfigParseError):
            collector_config_service.parse_collector_config(cr)


class TestBuildCollectorInstance:
    """Test building CollectorInstance from CRD."""

    def test_build_summary(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        instance = collector_config_service.build_collector_instance(
            sample_collector_cr, cfg, detail_level="summary"
        )
        assert instance.name == "my-collector"
        assert instance.namespace == "observability"
        assert instance.mode == "daemonset"
        assert instance.raw_config_yaml is None
        assert len(instance.pipelines) == 3
        assert instance.spanmetrics_enabled is True

    def test_build_full(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        instance = collector_config_service.build_collector_instance(
            sample_collector_cr, cfg, detail_level="full"
        )
        assert instance.raw_config_yaml is not None
        assert "receivers" in instance.raw_config_yaml


class TestExtractPipelines:
    """Test pipeline extraction."""

    def test_extract_all_pipelines(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        pipelines = collector_config_service.extract_pipelines(cfg)
        assert len(pipelines) == 3
        signals = [p.signal for p in pipelines]
        assert "traces" in signals
        assert "metrics" in signals
        assert "logs" in signals

    def test_pipeline_components(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        pipelines = collector_config_service.extract_pipelines(cfg)
        traces = next(p for p in pipelines if p.signal == "traces")
        receiver_types = [r.type for r in traces.receivers]
        assert "otlp" in receiver_types


class TestExtractK8sEnrichment:
    """Test k8sattributes extraction."""

    def test_enabled_enrichment(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        profile = collector_config_service.extract_k8s_enrichment(
            cfg, "my-collector", "observability"
        )
        assert profile.enabled is True
        assert "k8s.pod.name" in profile.extract_metadata

    def test_disabled_enrichment(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        from opentelemetry_mcp_server.utils.yaml_helpers import safe_load_yaml

        cfg = safe_load_yaml(
            "receivers:\n  otlp:\n    protocols:\n      grpc: {}\n"
            "processors:\n  batch: {}\n"
            "exporters:\n  otlp:\n    endpoint: tempo:4317\n"
            "service:\n  pipelines:\n    traces:\n      receivers: [otlp]\n"
            "      processors: [batch]\n      exporters: [otlp]\n"
        )
        profile = collector_config_service.extract_k8s_enrichment(
            cfg, "simple", "default"
        )
        assert profile.enabled is False


class TestExtractLogsProfile:
    """Test filelog receiver extraction."""

    def test_logs_profile(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        profile = collector_config_service.extract_logs_profile(
            cfg, "my-collector", "observability"
        )
        assert profile.enabled is True
        assert len(profile.filelog_receivers) == 1
        assert profile.has_storage_checkpoint is True
        assert profile.has_exclude_self is True


class TestExtractSpanmetricsProfile:
    """Test spanmetrics extraction."""

    def test_spanmetrics_profile(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        profile = collector_config_service.extract_spanmetrics_profile(
            cfg, "my-collector", "observability"
        )
        assert profile.enabled is True
        assert len(profile.dimensions) == 3
        assert profile.source_pipeline == "traces"
        assert profile.target_pipeline == "metrics"


class TestSamplingDetection:
    """Test sampling mode detection."""

    def test_detect_tail_sampling(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        mode = collector_config_service.detect_sampling_mode(cfg, None)
        assert mode == "tail"

    def test_detect_head_sampling(
        self,
        collector_config_service: CollectorConfigService,
        sample_instrumentation_cr: dict,
    ) -> None:
        from opentelemetry_mcp_server.utils.yaml_helpers import safe_load_yaml

        cfg = safe_load_yaml(
            "receivers:\n  otlp: {}\nservice:\n  pipelines:\n"
            "    traces:\n      receivers: [otlp]"
        )
        mode = collector_config_service.detect_sampling_mode(
            cfg, sample_instrumentation_cr
        )
        assert mode == "head"

    def test_extract_full_sampling_config(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
        sample_instrumentation_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        sampling = collector_config_service.extract_sampling_config(
            cfg, "my-collector", "observability", sample_instrumentation_cr
        )
        assert sampling.mode == "tail"
        assert sampling.head_sampler_type == "parentbased_traceidratio"
        assert sampling.head_sample_rate == 0.25
        assert len(sampling.tail_policies) == 2
        # Should warn about head+tail conflict
        assert any(
            "head" in w.lower() and "tail" in w.lower() for w in sampling.warnings
        )


class TestValidateProcessorOrder:
    """Test processor ordering validation."""

    def test_valid_order(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        result = collector_config_service.validate_processor_order(
            cfg,
            "traces",
            ["memory_limiter", "k8sattributes", "tail_sampling", "batch"],
        )
        assert result["valid"] is True

    def test_missing_pipeline(
        self,
        collector_config_service: CollectorConfigService,
        sample_collector_cr: dict,
    ) -> None:
        cfg = collector_config_service.parse_collector_config(sample_collector_cr)
        result = collector_config_service.validate_processor_order(
            cfg, "nonexistent", ["batch"]
        )
        assert result["valid"] is False


class TestGenerateTransformSnippet:
    """Test transform processor YAML generation."""

    def test_generate_snippet(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        snippet = collector_config_service.generate_transform_snippet(
            ["http.user_agent", "url.full"]
        )
        assert "processors:" in snippet
        assert "http.user_agent" in snippet
        assert "url.full" in snippet

    def test_empty_attributes(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        snippet = collector_config_service.generate_transform_snippet([])
        assert "No attributes" in snippet

    def test_snippet_is_valid_yaml(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        """Generated snippet must parse as valid YAML."""
        import yaml

        snippet = collector_config_service.generate_transform_snippet(
            ["http.user_agent", "url.full"]
        )
        parsed = yaml.safe_load(snippet)
        assert parsed is not None
        assert "processors" in parsed

    def test_snippet_structure(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        """Generated snippet must have correct nested structure."""
        import yaml

        snippet = collector_config_service.generate_transform_snippet(
            ["http.user_agent", "url.full"]
        )
        parsed = yaml.safe_load(snippet)
        proc = parsed["processors"]["transform/drop_attributes"]
        statements_block = proc["metric_statements"][0]
        assert statements_block["context"] == "datapoint"
        assert len(statements_block["statements"]) == 2
        assert 'delete_key(attributes, "http.user_agent")' in statements_block["statements"]
        assert 'delete_key(attributes, "url.full")' in statements_block["statements"]


class TestSpanmetricsDurationBuckets:
    """Test spanmetrics extraction with OTel duration-string buckets."""

    def test_duration_buckets_from_otel_demo(
        self, collector_config_service: CollectorConfigService
    ) -> None:
        """Duration-string buckets in connector config must parse correctly."""
        cr = {
            "metadata": {"name": "test", "namespace": "default"},
            "spec": {
                "mode": "deployment",
                "config": {
                    "connectors": {
                        "spanmetrics": {
                            "histogram": {
                                "explicit": {
                                    "buckets": [
                                        "2ms", "100ms", "1s", "15s",
                                    ],
                                }
                            },
                            "dimensions": [{"name": "http.method"}],
                        }
                    },
                    "receivers": {"otlp": {"protocols": {"grpc": {}}}},
                    "exporters": {"otlp": {"endpoint": "tempo:4317"}},
                    "service": {
                        "pipelines": {
                            "traces": {
                                "receivers": ["otlp"],
                                "exporters": ["spanmetrics", "otlp"],
                            },
                            "metrics": {
                                "receivers": ["spanmetrics"],
                                "exporters": ["otlp"],
                            },
                        }
                    },
                },
            },
        }
        cfg = collector_config_service.parse_collector_config(cr)
        profile = collector_config_service.extract_spanmetrics_profile(
            cfg, "test", "default"
        )
        assert profile.enabled is True
        assert profile.histogram.explicit_buckets == [
            2.0, 100.0, 1000.0, 15000.0,
        ]

