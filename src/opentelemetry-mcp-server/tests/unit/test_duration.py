"""Unit tests for OTel duration string parsing and formatting utilities."""

import pytest

from opentelemetry_mcp_server.utils.duration import (
    format_bucket_list,
    ms_to_duration_string,
    parse_bucket_list,
    parse_duration_to_ms,
)


class TestParseDurationToMs:
    """Tests for parse_duration_to_ms()."""

    def test_numeric_int(self) -> None:
        assert parse_duration_to_ms(500) == 500.0

    def test_numeric_float(self) -> None:
        assert parse_duration_to_ms(1.5) == 1.5

    def test_milliseconds(self) -> None:
        assert parse_duration_to_ms("2ms") == 2.0

    def test_milliseconds_uppercase(self) -> None:
        assert parse_duration_to_ms("100MS") == 100.0

    def test_seconds(self) -> None:
        assert parse_duration_to_ms("1s") == 1000.0

    def test_seconds_fractional(self) -> None:
        assert parse_duration_to_ms("1.5s") == 1500.0

    def test_minutes(self) -> None:
        assert parse_duration_to_ms("1m") == 60000.0

    def test_hours(self) -> None:
        assert parse_duration_to_ms("1h") == 3600000.0

    def test_microseconds(self) -> None:
        assert parse_duration_to_ms("1000us") == 1.0

    def test_nanoseconds(self) -> None:
        assert parse_duration_to_ms("1000000ns") == 1.0

    def test_whitespace_handling(self) -> None:
        assert parse_duration_to_ms("  2ms  ") == 2.0

    def test_unitless_defaults_to_ms(self) -> None:
        assert parse_duration_to_ms("100") == 100.0

    def test_zero(self) -> None:
        assert parse_duration_to_ms("0ms") == 0.0
        assert parse_duration_to_ms(0) == 0.0

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse duration"):
            parse_duration_to_ms("abc")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse duration"):
            parse_duration_to_ms("")

    def test_otel_demo_buckets(self) -> None:
        """Test the exact bucket values from OTel Demo CRD."""
        buckets = ["2ms", "4ms", "6ms", "8ms", "10ms", "50ms", "100ms",
                   "200ms", "400ms", "800ms", "1s", "1400ms", "2s",
                   "5s", "10s", "15s"]
        expected = [2, 4, 6, 8, 10, 50, 100, 200, 400, 800, 1000,
                    1400, 2000, 5000, 10000, 15000]
        for b, exp in zip(buckets, expected):
            assert parse_duration_to_ms(b) == exp


class TestMsToDurationString:
    """Tests for ms_to_duration_string()."""

    def test_milliseconds(self) -> None:
        assert ms_to_duration_string(2.0) == "2ms"

    def test_seconds(self) -> None:
        assert ms_to_duration_string(1000.0) == "1s"

    def test_minutes(self) -> None:
        assert ms_to_duration_string(60000.0) == "1m"

    def test_hours(self) -> None:
        assert ms_to_duration_string(3600000.0) == "1h"

    def test_non_round_seconds_stays_ms(self) -> None:
        assert ms_to_duration_string(1500.0) == "1500ms"

    def test_non_round_minutes_stays_seconds(self) -> None:
        assert ms_to_duration_string(90000.0) == "90s"

    def test_zero(self) -> None:
        assert ms_to_duration_string(0) == "0ms"

    def test_large_ms_value(self) -> None:
        assert ms_to_duration_string(15000.0) == "15s"

    def test_1400ms(self) -> None:
        assert ms_to_duration_string(1400.0) == "1400ms"


class TestParseBucketList:
    """Tests for parse_bucket_list()."""

    def test_mixed_input(self) -> None:
        result = parse_bucket_list(["2ms", 100, "1s", 15000.0])
        assert result == [2.0, 100.0, 1000.0, 15000.0]

    def test_all_strings(self) -> None:
        result = parse_bucket_list(["2ms", "1s", "15s"])
        assert result == [2.0, 1000.0, 15000.0]

    def test_all_numbers(self) -> None:
        result = parse_bucket_list([2, 100, 1000])
        assert result == [2.0, 100.0, 1000.0]


class TestFormatBucketList:
    """Tests for format_bucket_list()."""

    def test_standard_buckets(self) -> None:
        result = format_bucket_list([2.0, 100.0, 1000.0, 15000.0])
        assert result == ["2ms", "100ms", "1s", "15s"]

    def test_otel_demo_round_trip(self) -> None:
        """Parse OTel Demo buckets then format back — values should round-trip."""
        original = ["2ms", "4ms", "6ms", "8ms", "10ms", "50ms", "100ms",
                     "200ms", "400ms", "800ms", "1s", "1400ms", "2s",
                     "5s", "10s", "15s"]
        parsed = parse_bucket_list(original)
        formatted = format_bucket_list(parsed)
        assert formatted == original
