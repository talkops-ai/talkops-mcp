"""Unit tests for LogQL helpers.

Per test guide §5: Pure logic tests, no MCP involved.
"""

import pytest

from loki_mcp_server.utils.logql_helpers import (
    detect_high_cardinality_in_selector,
    format_log_entries,
    suggest_pattern_from_lines,
    validate_stream_selector,
)
from loki_mcp_server.exceptions import LokiValidationError


class TestValidateStreamSelector:
    def test_valid_simple_selector(self):
        validate_stream_selector('{app="checkout"}')

    def test_valid_multi_label(self):
        validate_stream_selector('{app="checkout", namespace="prod"}')

    def test_valid_regex_selector(self):
        validate_stream_selector('{app=~"check.*"}')

    def test_empty_query_raises(self):
        with pytest.raises(LokiValidationError, match="must not be empty"):
            validate_stream_selector("")

    def test_valid_metric_query(self):
        validate_stream_selector('rate({app="checkout"} [5m])')

    def test_no_braces_raises(self):
        with pytest.raises(LokiValidationError, match="MUST be wrapped in curly braces"):
            validate_stream_selector('rate(app="checkout" [5m])')

    def test_unbalanced_braces_raises(self):
        with pytest.raises(LokiValidationError, match="unbalanced"):
            validate_stream_selector('{app="checkout"')


class TestDetectHighCardinality:
    def test_no_high_cardinality(self):
        result = detect_high_cardinality_in_selector('{app="checkout"}')
        assert result == []

    def test_trace_id_detected(self):
        result = detect_high_cardinality_in_selector(
            '{app="checkout", trace_id="abc123"}'
        )
        assert "trace_id" in result

    def test_user_id_detected(self):
        result = detect_high_cardinality_in_selector(
            '{user_id="user-123"}'
        )
        assert "user_id" in result

    def test_multiple_detected(self):
        result = detect_high_cardinality_in_selector(
            '{app="checkout", trace_id="abc", ip="1.2.3.4"}'
        )
        assert "trace_id" in result
        assert "ip" in result

    def test_case_variant_traceID(self):
        result = detect_high_cardinality_in_selector(
            '{traceID="abc123"}'
        )
        assert "traceID" in result


class TestFormatLogEntries:
    def test_basic_formatting(self):
        streams = [
            {
                "stream": {"app": "checkout"},
                "values": [["1700000000", "log line 1"], ["1700000001", "log line 2"]],
            }
        ]
        result = format_log_entries(streams, max_lines=10)
        assert len(result) == 1
        assert len(result[0]["entries"]) == 2
        assert result[0]["entries"][0]["line"] == "log line 1"

    def test_truncation(self):
        streams = [
            {
                "stream": {"app": "checkout"},
                "values": [
                    [str(i), f"line {i}"] for i in range(100)
                ],
            }
        ]
        result = format_log_entries(streams, max_lines=5)
        total = sum(len(s["entries"]) for s in result)
        assert total == 5


class TestSuggestPattern:
    def test_json_detection(self):
        lines = [
            '{"timestamp":"2024-01-01","level":"error","message":"failed"}',
            '{"timestamp":"2024-01-01","level":"info","message":"ok"}',
            '{"timestamp":"2024-01-01","level":"warn","message":"slow"}',
        ]
        result = suggest_pattern_from_lines(lines)
        assert result == "| json"

    def test_logfmt_detection(self):
        lines = [
            "level=info msg=started duration=45ms",
            "level=error msg=failed duration=100ms",
            "level=warn msg=slow duration=200ms",
        ]
        result = suggest_pattern_from_lines(lines)
        assert result == "| logfmt"

    def test_insufficient_lines(self):
        result = suggest_pattern_from_lines(["single line"])
        assert result is None

    def test_empty_lines(self):
        result = suggest_pattern_from_lines([])
        assert result is None
