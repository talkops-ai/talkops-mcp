"""Unit tests for metrics time range validation.

B-02: Validates that the MCP server pre-validates metrics query time
ranges against the configured max_metrics_duration before hitting Tempo.
"""

import time

import pytest

from tempo_mcp_server.exceptions.custom import TempoValidationError
from tempo_mcp_server.tools.metrics.metrics_tools import _validate_metrics_time_range
from tempo_mcp_server.utils.time_helpers import duration_to_seconds


class TestDurationToSeconds:
    """Verify the duration_to_seconds utility."""

    def test_hours(self):
        assert duration_to_seconds("3h") == 10800.0

    def test_minutes(self):
        assert duration_to_seconds("30m") == 1800.0

    def test_seconds(self):
        assert duration_to_seconds("60s") == 60.0

    def test_days(self):
        assert duration_to_seconds("7d") == 604800.0

    def test_weeks(self):
        assert duration_to_seconds("2w") == 1209600.0

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid duration format"):
            duration_to_seconds("3hours")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="Invalid duration format"):
            duration_to_seconds("")


class TestMetricsTimeRangeValidation:
    """B-02: Pre-validation of metrics query time ranges."""

    def test_rejects_range_exceeding_max(self):
        """6h range should be rejected when max is 3h."""
        now = time.time()
        start = now - (6 * 3600)  # 6 hours ago
        end = now

        with pytest.raises(TempoValidationError, match="exceeds the maximum"):
            _validate_metrics_time_range(start, end, "3h")

    def test_accepts_range_within_max(self):
        """2h range should pass when max is 3h."""
        now = time.time()
        start = now - (2 * 3600)  # 2 hours ago
        end = now

        # Should not raise
        _validate_metrics_time_range(start, end, "3h")

    def test_accepts_exact_max(self):
        """Exactly 3h should pass when max is 3h."""
        now = time.time()
        start = now - (3 * 3600)
        end = now

        # Should not raise (edge case: exactly at limit)
        _validate_metrics_time_range(start, end, "3h")

    def test_skips_when_start_is_none(self):
        """Should be a no-op when start is not resolved."""
        _validate_metrics_time_range(None, time.time(), "3h")

    def test_skips_when_end_is_none(self):
        """Should be a no-op when end is not resolved."""
        _validate_metrics_time_range(time.time(), None, "3h")

    def test_actionable_error_message(self):
        """Error message should guide the user to narrow the range."""
        now = time.time()
        start = now - (6 * 3600)

        with pytest.raises(TempoValidationError) as exc_info:
            _validate_metrics_time_range(start, now, "3h")

        error_msg = str(exc_info.value)
        assert "6.0h" in error_msg
        assert "3.0h" in error_msg
        assert "max_duration" in error_msg
        assert "narrow" in error_msg.lower() or "Narrow" in error_msg

    def test_invalid_max_duration_config_skips_validation(self):
        """Invalid config value should not crash; just skip validation."""
        now = time.time()
        start = now - (6 * 3600)

        # Should not raise despite 6h range — config is invalid, skip validation
        _validate_metrics_time_range(start, now, "invalid")

    def test_custom_max_duration(self):
        """Should respect non-default max durations."""
        now = time.time()
        start = now - (12 * 3600)  # 12 hours

        # With 24h max, 12h should pass
        _validate_metrics_time_range(start, now, "24h")

        # With 6h max, 12h should fail
        with pytest.raises(TempoValidationError):
            _validate_metrics_time_range(start, now, "6h")
