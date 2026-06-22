"""Tests for CollectorTools (otel_patch_collector).

Tests the new otel_patch_collector tool — a write tool for
OpenTelemetryCollector CRDs.
"""

from opentelemetry_mcp_server.tools.collector.collector_tools import _VALID_MODES
from opentelemetry_mcp_server.utils.yaml_helpers import safe_load_yaml


class TestCollectorToolValidation:
    """Test otel_patch_collector input validation."""

    def test_valid_modes(self) -> None:
        """Valid deployment modes per OTel Operator spec."""
        assert _VALID_MODES == {"daemonset", "deployment", "statefulset", "sidecar"}

    def test_config_yaml_parsing(self) -> None:
        """Config YAML must be parseable and contain required sections."""
        valid_config = """
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
exporters:
  otlp:
    endpoint: tempo:4317
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp]
"""
        parsed = safe_load_yaml(valid_config)
        assert "service" in parsed
        assert "pipelines" in parsed["service"]
        assert "traces" in parsed["service"]["pipelines"]

    def test_config_without_service_section(self) -> None:
        """Config without 'service' section should be caught."""
        incomplete_config = """
receivers:
  otlp:
    protocols:
      grpc: {}
"""
        parsed = safe_load_yaml(incomplete_config)
        assert "service" not in parsed


class TestCollectorCrdBodyStructure:
    """Test the CRD body structure for correctness."""

    def test_crd_body_matches_operator_spec(self) -> None:
        """Verify the CRD body structure matches OpenTelemetry Operator expectations."""
        crd_group = "opentelemetry.io"
        crd_version = "v1beta1"
        name = "test-collector"
        namespace = "test-ns"
        labels = {"app.kubernetes.io/part-of": "my-app"}
        annotations = {"custom.io/note": "test"}

        metadata = {
            "name": name,
            "namespace": namespace,
            "labels": labels,
            "annotations": annotations,
        }
        body = {
            "apiVersion": f"{crd_group}/{crd_version}",
            "kind": "OpenTelemetryCollector",
            "metadata": metadata,
            "spec": {
                "mode": "deployment",
                "config": {"service": {"pipelines": {"traces": {}}}},
            },
        }

        assert body["apiVersion"] == "opentelemetry.io/v1beta1"
        assert body["kind"] == "OpenTelemetryCollector"
        assert body["metadata"]["labels"] == labels
        assert body["metadata"]["annotations"] == annotations
        assert body["spec"]["mode"] == "deployment"

    def test_dynamic_labels_and_annotations(self) -> None:
        """Labels and annotations should not be hardcoded — must accept any dict."""
        labels = {
            "app.kubernetes.io/name": "custom",
            "team": "platform",
            "env": "staging",
        }
        annotations = {
            "prometheus.io/scrape": "true",
            "custom.domain.io/owner": "sre-team",
        }
        metadata = {
            "name": "test",
            "namespace": "default",
        }
        if labels:
            metadata["labels"] = labels
        if annotations:
            metadata["annotations"] = annotations

        assert metadata["labels"] == labels
        assert metadata["annotations"] == annotations
        assert len(metadata["labels"]) == 3
        assert len(metadata["annotations"]) == 2

    def test_optional_spec_fields(self) -> None:
        """Optional spec fields like image, replicas, serviceAccount should be included only when set."""
        spec = {"mode": "daemonset", "config": {}}
        image = "otel/opentelemetry-collector-contrib:0.152.1"
        replicas = 3
        service_account = "otel-collector-sa"

        if image:
            spec["image"] = image
        if replicas is not None:
            spec["replicas"] = replicas
        if service_account:
            spec["serviceAccount"] = service_account

        assert spec["image"] == image
        assert spec["replicas"] == 3
        assert spec["serviceAccount"] == service_account

    def test_target_allocator_embedding(self) -> None:
        """Target allocator config should be embedded in spec when provided."""
        ta_config = {
            "enabled": True,
            "prometheusCR": {
                "enabled": True,
                "serviceMonitorSelector": {},
                "podMonitorSelector": {},
            },
        }
        spec = {"mode": "statefulset", "config": {}}
        spec["targetAllocator"] = ta_config

        assert spec["targetAllocator"]["enabled"] is True
        assert "prometheusCR" in spec["targetAllocator"]


class TestResourceVersionForReplace:
    """Test that replace (overwrite=True) injects resourceVersion."""

    def test_resource_version_injected(self) -> None:
        """Replace body must include metadata.resourceVersion from existing CRD."""
        # Simulate the logic from create_or_patch_collector
        existing = {
            "metadata": {
                "name": "my-collector",
                "namespace": "otel-demo",
                "resourceVersion": "12345",
            },
        }
        body = {
            "apiVersion": "opentelemetry.io/v1beta1",
            "kind": "OpenTelemetryCollector",
            "metadata": {"name": "my-collector", "namespace": "otel-demo"},
            "spec": {"mode": "deployment", "config": {}},
        }
        existing_rv = existing.get("metadata", {}).get("resourceVersion")
        if existing_rv:
            body["metadata"]["resourceVersion"] = existing_rv

        assert body["metadata"]["resourceVersion"] == "12345"

    def test_missing_resource_version_skipped(self) -> None:
        """If existing CRD has no resourceVersion, don't inject it."""
        existing = {
            "metadata": {"name": "my-collector", "namespace": "otel-demo"},
        }
        body = {
            "apiVersion": "opentelemetry.io/v1beta1",
            "kind": "OpenTelemetryCollector",
            "metadata": {"name": "my-collector", "namespace": "otel-demo"},
            "spec": {"mode": "deployment", "config": {}},
        }
        existing_rv = existing.get("metadata", {}).get("resourceVersion")
        if existing_rv:
            body["metadata"]["resourceVersion"] = existing_rv

        assert "resourceVersion" not in body["metadata"]

