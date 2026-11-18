"""Unit tests for deep secret redaction and bounded write audit logging."""

from __future__ import annotations

from pathlib import Path

from prometheus_mcp_server.utils.audit import (
    add_audit_entry,
    clear_audit_log,
    get_audit_entries,
)
from prometheus_mcp_server.utils.redaction import (
    REDACTED_VALUE,
    is_secret_key,
    redact_sensitive_data,
    redact_string_secrets,
)


class TestRedactionAndAudit:
    def test_secret_key_detection_and_recursive_redaction(self) -> None:
        assert is_secret_key("bearer_token") is True
        assert is_secret_key("REDIS_PASSWORD") is True
        assert is_secret_key("scrape_interval") is False

        raw = {
            "global": {"scrape_interval": "15s"},
            "remote_write": [
                {
                    "url": "https://admin:s3cr3t@mimir.example.com/api/v1/push",
                    "basic_auth": {"username": "admin", "password": "plain-password"},
                    "oauth2": {"client_secret": "oauth-secret"},
                }
            ],
            "env": [
                {"name": "REDIS_ADDR", "value": "redis://redis:6379"},
                {"name": "REDIS_PASSWORD", "value": "my-redis-secret"},
            ],
        }
        redacted = redact_sensitive_data(raw)
        assert redacted["global"]["scrape_interval"] == "15s"
        rw = redacted["remote_write"][0]
        assert rw["url"] == "https://***:***@mimir.example.com/api/v1/push"
        assert rw["basic_auth"]["password"] == REDACTED_VALUE
        assert rw["oauth2"]["client_secret"] == REDACTED_VALUE
        assert redacted["env"][0]["value"] == "redis://redis:6379"
        assert redacted["env"][1]["value"] == REDACTED_VALUE

    def test_dsn_and_k8s_secret_redaction(self) -> None:
        dsn = "user=postgres password=supersecret host=db.internal port=5432"
        masked = redact_string_secrets(dsn)
        assert "supersecret" not in masked
        assert f"password={REDACTED_VALUE}" in masked

        k8s_secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "exporter-secret"},
            "data": {"dsn": "base64blob"},
            "stringData": {"password": "cleartext"},
        }
        redacted_secret = redact_sensitive_data(k8s_secret)
        assert redacted_secret["data"]["dsn"] == REDACTED_VALUE
        assert redacted_secret["stringData"]["password"] == REDACTED_VALUE

    def test_audit_log_ring_buffer_and_jsonl_persistence(self, tmp_path: Path) -> None:
        clear_audit_log()
        log_file = tmp_path / "audit.jsonl"

        entry = add_audit_entry(
            backend_id="default",
            operation="prom_upsert_rule_group",
            summary="Applied rule group 'api-slo'",
            outcome="succeeded",
            details={"group": "api-slo", "auth_token": "leak-me-not"},
            audit_log_path=str(log_file),
        )
        assert entry.details["auth_token"] == REDACTED_VALUE

        recent = get_audit_entries(limit=10)
        assert len(recent) == 1
        assert recent[0]["operation"] == "prom_upsert_rule_group"

        assert log_file.exists()
        file_text = log_file.read_text(encoding="utf-8")
        assert "leak-me-not" not in file_text
        assert REDACTED_VALUE in file_text
        clear_audit_log()
        # Even after clearing in-memory buffer, get_audit_entries reloads from disk JSONL
        reloaded = get_audit_entries(limit=10, audit_log_path=str(log_file))
        assert len(reloaded) == 1
        assert reloaded[0]["operation"] == "prom_upsert_rule_group"
