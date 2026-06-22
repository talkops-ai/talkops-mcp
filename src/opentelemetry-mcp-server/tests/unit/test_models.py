"""Tests for Pydantic models."""

from opentelemetry_mcp_server.models import (
    CollectorInstance,
    HistogramBucketConfig,
    K8sEnrichmentProfile,
    PaginatedResponse,
    PipelineSpec,
    ReceiverRef,
    SamplingConfig,
)


class TestCollectorInstance:
    """Test CollectorInstance model."""

    def test_default_values(self) -> None:
        instance = CollectorInstance(
            name="test",
            namespace="default",
            mode="deployment",
        )
        assert instance.name == "test"
        assert instance.mode == "deployment"
        assert instance.pipelines == []
        assert instance.spanmetrics_enabled is False
        assert instance.raw_config_yaml is None

    def test_serialization(self) -> None:
        instance = CollectorInstance(
            name="test",
            namespace="default",
            mode="daemonset",
            version="0.102.0",
            pipelines=[
                PipelineSpec(
                    name="traces",
                    signal="traces",
                    receivers=[ReceiverRef(name="otlp", type="otlp")],
                    processors=[],
                    exporters=[],
                )
            ],
        )
        data = instance.model_dump()
        assert data["name"] == "test"
        assert len(data["pipelines"]) == 1
        assert data["pipelines"][0]["signal"] == "traces"


class TestPaginatedResponse:
    """Test PaginatedResponse generic model."""

    def test_pagination_model(self) -> None:
        resp = PaginatedResponse[str](
            items=["a", "b", "c"],
            total_count=10,
            next_cursor="abc123",
            page_size=3,
        )
        assert len(resp.items) == 3
        assert resp.total_count == 10
        assert resp.next_cursor == "abc123"

    def test_last_page(self) -> None:
        resp = PaginatedResponse[str](
            items=["x"],
            total_count=1,
            next_cursor=None,
            page_size=50,
        )
        assert resp.next_cursor is None


class TestK8sEnrichmentProfile:
    """Test K8sEnrichmentProfile model."""

    def test_disabled_profile(self) -> None:
        profile = K8sEnrichmentProfile(
            collector_name="test",
            collector_namespace="default",
            enabled=False,
        )
        assert profile.enabled is False
        assert profile.extract_metadata == []

    def test_enabled_profile(self) -> None:
        profile = K8sEnrichmentProfile(
            collector_name="test",
            collector_namespace="default",
            enabled=True,
            extract_metadata=["k8s.pod.name", "k8s.namespace.name"],
        )
        assert profile.enabled is True
        assert "k8s.pod.name" in profile.extract_metadata


class TestSamplingConfig:
    """Test SamplingConfig model."""

    def test_no_sampling(self) -> None:
        cfg = SamplingConfig(
            collector_name="test",
            collector_namespace="default",
            mode="none",
        )
        assert cfg.mode == "none"
        assert cfg.head_sampler_type is None
        assert cfg.tail_policies == []

    def test_head_sampling(self) -> None:
        cfg = SamplingConfig(
            collector_name="test",
            collector_namespace="default",
            mode="head",
            head_sampler_type="parentbased_traceidratio",
            head_sample_rate=0.25,
        )
        assert cfg.mode == "head"
        assert cfg.head_sample_rate == 0.25


class TestHistogramBucketConfig:
    """Test HistogramBucketConfig model with OTel duration strings."""

    def test_duration_strings_parsed(self) -> None:
        """Duration strings like '2ms', '1s' should parse to floats."""
        config = HistogramBucketConfig(
            explicit_buckets=["2ms", "4ms", "100ms", "1s", "15s"]
        )
        assert config.explicit_buckets == [2.0, 4.0, 100.0, 1000.0, 15000.0]

    def test_mixed_types_parsed(self) -> None:
        """Mix of strings and numbers should all parse correctly."""
        config = HistogramBucketConfig(
            explicit_buckets=["2ms", 100, "1s", 15000.0]
        )
        assert config.explicit_buckets == [2.0, 100.0, 1000.0, 15000.0]

    def test_numeric_only_still_works(self) -> None:
        """Purely numeric input should still work."""
        config = HistogramBucketConfig(
            explicit_buckets=[2, 4, 6, 8, 10]
        )
        assert config.explicit_buckets == [2.0, 4.0, 6.0, 8.0, 10.0]

    def test_none_buckets(self) -> None:
        """None input should stay None."""
        config = HistogramBucketConfig(explicit_buckets=None)
        assert config.explicit_buckets is None

    def test_otel_demo_buckets(self) -> None:
        """Full OTel Demo bucket list should parse without error."""
        otel_demo_buckets = [
            "2ms", "4ms", "6ms", "8ms", "10ms", "50ms", "100ms",
            "200ms", "400ms", "800ms", "1s", "1400ms", "2s",
            "5s", "10s", "15s",
        ]
        config = HistogramBucketConfig(explicit_buckets=otel_demo_buckets)
        assert len(config.explicit_buckets) == 16
        assert config.explicit_buckets[0] == 2.0
        assert config.explicit_buckets[10] == 1000.0  # 1s
        assert config.explicit_buckets[-1] == 15000.0  # 15s

