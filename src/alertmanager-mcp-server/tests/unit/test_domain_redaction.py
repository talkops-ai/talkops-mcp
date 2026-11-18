"""Unit tests for `alertmanager_mcp_server.domain.redaction`."""

from __future__ import annotations

import yaml

from alertmanager_mcp_server.domain.redaction import (
    REDACTED_VALUE,
    redact_config_data,
    redact_url_userinfo,
)
from tests.conftest import SAMPLE_COMPLEX_CONFIG_YAML


class TestSecretRedaction:
    def test_redacts_nested_http_config_credentials_and_headers(self) -> None:
        """Regression test for P8: `http_config.authorization.credentials` must be redacted."""
        raw_cfg = yaml.safe_load(SAMPLE_COMPLEX_CONFIG_YAML)
        redacted = redact_config_data(raw_cfg)
        dumped = yaml.safe_dump(redacted)

        assert "global-smtp-secret-password" not in dumped
        assert "SECRET_DEFAULT" not in dumped
        assert "SECRET_PAY" not in dumped
        assert "pd-secret-routing-key-123" not in dumped
        assert "super-secret-bearer-token" not in dumped
        assert "custom-header-secret" not in dumped
        assert "user:pass123@" not in dumped

        # Verify structural metadata is preserved
        receivers = {r["name"]: r for r in redacted["receivers"]}
        pd = receivers["payments-pagerduty"]["pagerduty_configs"][0]
        assert pd["routing_key"] == REDACTED_VALUE
        assert pd["http_config"]["authorization"]["credentials"] == REDACTED_VALUE
        assert pd["http_config"]["headers"]["X-Custom-Auth"] == REDACTED_VALUE

        wh = receivers["payments-audit-webhook"]["webhook_configs"][0]
        assert wh["url"] == "https://***:***@webhook.internal.example.com/hook"

    def test_redact_url_userinfo_preserves_clean_urls(self) -> None:
        assert (
            redact_url_userinfo("https://admin:s3cr3t@am.internal:9093/api")
            == "https://***:***@am.internal:9093/api"
        )
        assert (
            redact_url_userinfo("https://am.internal:9093/api")
            == "https://am.internal:9093/api"
        )
