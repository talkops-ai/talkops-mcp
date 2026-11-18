"""Unit tests for redaction, K8s manifest sanitization, unified diff, and Prometheus text exposition."""

from tempo_mcp_server.utils.prom_text import (
    extract_tempo_metrics_facts,
    parse_prometheus_text,
)
from tempo_mcp_server.utils.redaction import (
    compute_unified_diff,
    extract_safe_status_config,
    redact_sensitive_dict,
    sanitize_k8s_manifest,
)


class TestRedactionAndSanitization:
    """Verify credential redaction, K8s metadata stripping, and safe config extraction."""

    def test_redact_sensitive_dict_masks_credentials(self):
        raw = {
            "storage": {
                "s3": {
                    "bucket": "tempo-traces",
                    "access_key_id": "AKIA123456",
                    "secret_access_key": "super-secret",
                }
            },
            "auth": {"bearer_token": "tok-xyz"},
        }
        redacted = redact_sensitive_dict(raw)
        assert redacted["storage"]["s3"]["bucket"] == "tempo-traces"
        assert redacted["storage"]["s3"]["access_key_id"] == "***REDACTED***"
        assert redacted["storage"]["s3"]["secret_access_key"] == "***REDACTED***"
        assert redacted["auth"]["bearer_token"] == "***REDACTED***"

    def test_sanitize_k8s_manifest_strips_managed_fields_and_last_applied(self):
        raw = {
            "apiVersion": "tempo.grafana.com/v1alpha1",
            "kind": "TempoStack",
            "metadata": {
                "name": "tempo-prod",
                "namespace": "observability",
                "managedFields": [{"manager": "kubectl"}],
                "annotations": {
                    "kubectl.kubernetes.io/last-applied-configuration": '{"big":"json"}',
                    "custom.io/owner": "platform",
                },
            },
            "spec": {"replicationFactor": 2},
        }
        clean = sanitize_k8s_manifest(raw)
        assert "managedFields" not in clean["metadata"]
        assert (
            "kubectl.kubernetes.io/last-applied-configuration"
            not in clean["metadata"]["annotations"]
        )
        assert clean["metadata"]["annotations"]["custom.io/owner"] == "platform"

    def test_extract_safe_status_config_allowlist_only(self):
        raw_cfg = {
            "multitenancy_enabled": True,
            "storage": {
                "trace": {
                    "backend": "s3",
                    "s3": {"secret_access_key": "DO_NOT_LEAK"},
                    "block": {"version": "vParquet4"},
                }
            },
            "metrics_generator": {
                "processors": ["service-graphs", "span-metrics", "local-blocks"]
            },
            "overrides": {"defaults": {"ingestion": {"rate_limit_bytes": 15000000}}},
        }
        safe = extract_safe_status_config(raw_cfg)
        assert safe["multitenancy_enabled"] is True
        assert safe["storage_backend"] == "s3"
        assert safe["block_version"] == "vParquet4"
        assert safe["metrics_generator_processors"] == [
            "service-graphs",
            "span-metrics",
            "local-blocks",
        ]
        assert "DO_NOT_LEAK" not in str(safe)

    def test_compute_unified_diff(self):
        before = {"max_bytes_per_trace": 5000000}
        after = {"max_bytes_per_trace": 10000000}
        diff = compute_unified_diff(before, after, fromfile="before", tofile="after")
        assert "-max_bytes_per_trace: 5000000" in diff
        assert "+max_bytes_per_trace: 10000000" in diff


class TestPrometheusTextParser:
    """Verify Prometheus text exposition parser for Tempo 2.x/3.x metrics."""

    def test_parse_and_extract_tempo_metrics_facts(self):
        sample_metrics = """
# HELP tempo_discarded_spans_total Total number of spans discarded.
# TYPE tempo_discarded_spans_total counter
tempo_discarded_spans_total{reason="rate_limited",tenant="team-a"} 42
tempo_discarded_spans_total{reason="max_bytes_per_trace_exceeded",tenant="team-b"} 0
# HELP tempo_ingest_group_partition_lag_seconds Kafka partition lag in Tempo 3.0.
# TYPE tempo_ingest_group_partition_lag_seconds gauge
tempo_ingest_group_partition_lag_seconds{partition="0",group="block-builder"} 3.75
"""
        parsed = parse_prometheus_text(sample_metrics)
        names = {s["name"] for s in parsed}
        assert "tempo_discarded_spans_total" in names
        assert "tempo_ingest_group_partition_lag_seconds" in names

        facts = extract_tempo_metrics_facts(sample_metrics)
        assert facts["discarded_spans_by_reason"]["rate_limited"] == 42.0
        assert facts["discarded_spans_by_tenant"]["team-a"]["rate_limited"] == 42.0
        assert facts["total_discarded_spans"] == 42.0
        assert facts["max_partition_lag_seconds"] == 3.75
        assert len(facts["partition_lags"]) == 1
        assert facts["partition_lags"][0]["partition"] == "0"
        assert facts["partition_lags"][0]["lag_seconds"] == 3.75
