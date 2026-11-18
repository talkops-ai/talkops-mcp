"""Unit tests for Kubernetes manifest sanitization, Secret redaction, and HTTP header redaction."""

from traefik_mcp_server.utils.redaction import (
    redact_headers,
    redact_static_config,
    sanitize_manifest,
)


def test_sanitize_manifest_strips_managed_fields_and_redacts_secret_data():
    raw_secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "my-tls",
            "namespace": "default",
            "uid": "111",
            "managedFields": [{"manager": "kubectl"}],
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": '{"secret":"leak"}',
                "keep.me": "yes",
            },
        },
        "data": {"tls.crt": "CERT_DATA", "tls.key": "PRIVATE_KEY_DATA"},
    }
    clean = sanitize_manifest(raw_secret)
    assert "managedFields" not in clean["metadata"]
    assert "uid" not in clean["metadata"]
    assert "kubectl.kubernetes.io/last-applied-configuration" not in clean["metadata"]["annotations"]
    assert clean["metadata"]["annotations"]["keep.me"] == "yes"
    assert clean["data"]["tls.crt"] == "[REDACTED]"
    assert clean["data"]["tls.key"] == "[REDACTED]"


def test_redact_headers_and_static_config():
    hdrs = {
        "Authorization": "Bearer secret-jwt",
        "X-Api-Key": "secret-key",
        "Content-Type": "application/json",
    }
    red_hdrs = redact_headers(hdrs)
    assert red_hdrs["Authorization"] == "[REDACTED]"
    assert red_hdrs["X-Api-Key"] == "[REDACTED]"
    assert red_hdrs["Content-Type"] == "application/json"

    static_cfg = {
        "certificatesResolvers": {
            "letsencrypt": {"acme": {"email": "ops@example.com", "apiKey": "dns-secret"}}
        }
    }
    red_cfg = redact_static_config(static_cfg)
    assert red_cfg["certificatesResolvers"]["letsencrypt"]["acme"]["apiKey"] == "[REDACTED]"
