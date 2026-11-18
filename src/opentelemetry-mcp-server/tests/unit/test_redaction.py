"""T-U6: Unit tests for secret redaction and K8s manifest sanitization (S2 & S5 fixes)."""

from __future__ import annotations

from opentelemetry_mcp_server.utils.redaction import (
    REDACTED_VALUE,
    detect_inline_secrets,
    redact_collector_config,
    redact_log_text,
    sanitize_k8s_manifest,
)


def test_redact_collector_config_masks_literals_but_preserves_env_placeholders():
    raw_cfg = {
        "exporters": {
            "otlphttp/vendor": {
                "endpoint": "https://otlp.vendor.com/v1/traces",
                "headers": {
                    "Authorization": "Bearer sk_live_9876543210abcdef",
                    "api_key": "literal-api-key-value",
                    "X-Safe-Env": "${env:OTEL_EXPORTER_AUTH_TOKEN}",
                    "X-Alt-Env": "${OTEL_API_KEY}",
                },
            }
        }
    }
    findings = detect_inline_secrets(raw_cfg)
    assert len(findings) >= 2

    redacted = redact_collector_config(raw_cfg)
    headers = redacted["exporters"]["otlphttp/vendor"]["headers"]
    assert headers["Authorization"] == REDACTED_VALUE
    assert headers["api_key"] == REDACTED_VALUE
    assert headers["X-Safe-Env"] == "${env:OTEL_EXPORTER_AUTH_TOKEN}"
    assert headers["X-Alt-Env"] == "${OTEL_API_KEY}"


def test_sanitize_k8s_manifest_strips_managed_fields_and_last_applied():
    raw_manifest = {
        "apiVersion": "opentelemetry.io/v1beta1",
        "kind": "OpenTelemetryCollector",
        "metadata": {
            "name": "otel-col",
            "namespace": "default",
            "managedFields": [{"manager": "kubectl"}],
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": '{"secret":"leak"}',
                "otel.mcp/previous-config": "H4sIAAAAAAAA...",
                "app.kubernetes.io/part-of": "demo",
            },
        },
        "spec": {
            "config": {
                "exporters": {
                    "otlp": {"headers": {"api_key": "literal-secret-key-val"}}
                }
            }
        },
    }
    sanitized = sanitize_k8s_manifest(raw_manifest)
    meta = sanitized["metadata"]
    assert "managedFields" not in meta
    assert "kubectl.kubernetes.io/last-applied-configuration" not in meta["annotations"]
    assert meta["annotations"]["otel.mcp/previous-config"] == "<snapshot-present>"
    assert (
        sanitized["spec"]["config"]["exporters"]["otlp"]["headers"]["api_key"]
        == REDACTED_VALUE
    )


def test_redact_log_text_masks_bearer_and_api_keys():
    log_line = '2026-04-01 ERROR export failed: Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret api_key=my_secret_123'
    cleaned = redact_log_text(log_line)
    assert "eyJhbGciOiJIUzI1NiJ9.secret" not in cleaned
    assert "my_secret_123" not in cleaned
