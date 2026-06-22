"""Unit tests for time utilities."""

import pytest

from loki_mcp_server.utils.time_utils import (
    ensure_rfc3339,
    parse_relative_time,
    validate_time_window,
)
from loki_mcp_server.exceptions import LokiValidationError


class TestParseRelativeTime:
    def test_now(self):
        result = parse_relative_time("now")
        assert "T" in result
        assert result.endswith("Z")

    def test_now_minus_1h(self):
        result = parse_relative_time("now-1h")
        assert "T" in result

    def test_now_minus_30m(self):
        result = parse_relative_time("now-30m")
        assert "T" in result

    def test_now_minus_7d(self):
        result = parse_relative_time("now-7d")
        assert "T" in result

    def test_rfc3339_passthrough(self):
        ts = "2024-01-01T00:00:00Z"
        result = parse_relative_time(ts)
        assert result == ts

    def test_epoch_passthrough(self):
        result = parse_relative_time("1700000000")
        assert result == "1700000000"

    def test_empty_raises(self):
        with pytest.raises(LokiValidationError, match="Empty"):
            parse_relative_time("")

    def test_invalid_raises(self):
        with pytest.raises(LokiValidationError, match="Invalid"):
            parse_relative_time("yesterday")


class TestValidateTimeWindow:
    def test_valid_window(self):
        validate_time_window(
            "2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", 24
        )

    def test_exceeds_max(self):
        with pytest.raises(LokiValidationError, match="exceeds maximum"):
            validate_time_window(
                "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", 24
            )

    def test_start_after_end_raises(self):
        with pytest.raises(LokiValidationError, match="must be before"):
            validate_time_window(
                "2024-01-02T00:00:00Z", "2024-01-01T00:00:00Z", 24
            )


class TestEnsureRfc3339:
    def test_rfc3339_passthrough(self):
        ts = "2024-01-01T00:00:00Z"
        assert ensure_rfc3339(ts) == ts

    def test_epoch_conversion(self):
        result = ensure_rfc3339("1700000000")
        assert "T" in result
        assert "Z" in result

    def test_relative_conversion(self):
        result = ensure_rfc3339("now")
        assert "T" in result
