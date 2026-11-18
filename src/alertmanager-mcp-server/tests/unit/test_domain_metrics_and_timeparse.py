"""Unit tests for `alertmanager_mcp_server.domain.metrics` and `timeparse`."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from alertmanager_mcp_server.domain.metrics import parse_prometheus_metrics
from alertmanager_mcp_server.domain.timeparse import (
    TimeValidationError,
    format_rfc3339_utc,
    parse_rfc3339,
    resolve_silence_window,
)
from tests.conftest import SAMPLE_METRICS_TEXT


class TestPrometheusMetricsParser:
    def test_parses_notification_and_reload_metrics(self) -> None:
        summary = parse_prometheus_metrics(SAMPLE_METRICS_TEXT)
        assert summary.config_last_reload_successful is True
        assert summary.config_last_reload_timestamp == "2025-03-29T10:00:00Z"
        assert summary.cluster_members == 3
        assert summary.cluster_failed_peers == 0
        assert summary.total_notifications == 175
        assert summary.total_failed_notifications == 3
        assert summary.degraded_integrations == ["pagerduty"]

        pd = summary.integrations["pagerduty"]
        assert pd.notifications_total == 45
        assert pd.notifications_failed_total == 3
        assert pd.healthy is False
        assert pd.failures_by_reason == {"server_error": 3.0}

        slack = summary.integrations["slack"]
        assert slack.healthy is True
        assert slack.failure_rate == 0.0


class TestTimeparse:
    def test_rejects_naive_timestamps_without_timezone_offset(self) -> None:
        """Regression test for P2: naive timestamps must be rejected."""
        with pytest.raises(TimeValidationError, match="missing an explicit timezone offset"):
            parse_rfc3339("2026-03-29T10:00:00", require_tz=True)

        with pytest.raises(TimeValidationError, match="full RFC3339 date-time"):
            parse_rfc3339("2026-03-29", require_tz=True)

    def test_parses_and_normalizes_timezone_offsets_to_utc(self) -> None:
        dt = parse_rfc3339("2026-03-29T15:30:00+05:30", require_tz=True)
        assert format_rfc3339_utc(dt) == "2026-03-29T10:00:00Z"

    def test_resolve_silence_window_rejects_inverted_or_past_windows(self) -> None:
        now = datetime(2026, 3, 29, 10, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(TimeValidationError, match="strictly after"):
            resolve_silence_window(
                starts_at="2026-03-29T12:00:00Z",
                ends_at="2026-03-29T11:00:00Z",
                now=now,
            )

        with pytest.raises(TimeValidationError, match="in the past"):
            resolve_silence_window(
                starts_at="2026-03-29T08:00:00Z",
                ends_at="2026-03-29T09:00:00Z",
                now=now,
            )
