"""Unit tests for trace diff engine.

Covers all 5 diff dimensions: structure, span counts, timing,
errors, and attributes.
"""

import pytest
from typing import Any, Dict, List, Optional

from tempo_mcp_server.utils.trace_differ import (
    diff_traces,
    _build_service_map,
    _diff_structure,
    _diff_span_counts,
    _diff_durations,
    _diff_errors,
    _diff_attributes,
    _is_error_span,
    _get_service_name,
    _total_duration_ms,
)


# ── Test Data Factories ──

def _make_span(
    name: str = "GET /api",
    service: str = "api-gateway",
    span_id: str = "aaa",
    parent_id: str = "",
    start_ns: int = 1000000000,
    end_ns: int = 1100000000,
    status_code: int = 0,
    status_message: str = "",
    attributes: Optional[List[Dict]] = None,
    events: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Create a synthetic span dict in OTLP-like format."""
    span: Dict[str, Any] = {
        "name": name,
        "spanId": span_id,
        "parentSpanId": parent_id,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "status": {"code": status_code, "message": status_message},
        "attributes": attributes or [],
        "_resource_attrs": {"service.name": service},
    }
    if events:
        span["events"] = events
    return span


def _make_trace(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrap spans in a minimal trace-like structure."""
    return {"spans": spans}


# ── Structural Diff ──

class TestDiffStructure:
    """Test service-level structural diffing."""

    def test_identical_services(self):
        map_a = {"svc-a": [{}], "svc-b": [{}]}
        map_b = {"svc-a": [{}], "svc-b": [{}]}
        result = _diff_structure(map_a, map_b)
        assert result["services_only_in_a"] == []
        assert result["services_only_in_b"] == []
        assert sorted(result["services_in_both"]) == ["svc-a", "svc-b"]

    def test_service_only_in_a(self):
        map_a = {"svc-a": [{}], "svc-b": [{}]}
        map_b = {"svc-b": [{}]}
        result = _diff_structure(map_a, map_b)
        assert result["services_only_in_a"] == ["svc-a"]
        assert result["services_only_in_b"] == []

    def test_service_only_in_b(self):
        map_a = {"svc-a": [{}]}
        map_b = {"svc-a": [{}], "svc-c": [{}]}
        result = _diff_structure(map_a, map_b)
        assert result["services_only_in_b"] == ["svc-c"]

    def test_completely_different_services(self):
        map_a = {"svc-a": [{}]}
        map_b = {"svc-b": [{}]}
        result = _diff_structure(map_a, map_b)
        assert result["services_only_in_a"] == ["svc-a"]
        assert result["services_only_in_b"] == ["svc-b"]
        assert result["services_in_both"] == []


# ── Span Count Diff ──

class TestDiffSpanCounts:
    """Test per-service span count deltas."""

    def test_equal_counts(self):
        map_a = {"svc-a": [{}, {}]}
        map_b = {"svc-a": [{}, {}]}
        result = _diff_span_counts(map_a, map_b)
        assert result["svc-a"]["delta"] == 0

    def test_more_spans_in_b(self):
        map_a = {"svc-a": [{}, {}]}
        map_b = {"svc-a": [{}, {}, {}]}
        result = _diff_span_counts(map_a, map_b)
        assert result["svc-a"]["a"] == 2
        assert result["svc-a"]["b"] == 3
        assert result["svc-a"]["delta"] == 1

    def test_service_missing_in_one_side(self):
        map_a = {"svc-a": [{}]}
        map_b = {"svc-b": [{}, {}]}
        result = _diff_span_counts(map_a, map_b)
        assert result["svc-a"]["a"] == 1
        assert result["svc-a"]["b"] == 0
        assert result["svc-b"]["a"] == 0
        assert result["svc-b"]["b"] == 2


# ── Duration Diff ──

class TestDiffDurations:
    """Test timing diffs."""

    def test_total_duration_from_nanoseconds(self):
        spans = [
            _make_span(start_ns=1_000_000_000, end_ns=1_200_000_000),
        ]
        ms = _total_duration_ms(spans)
        assert ms == 200.0  # 200ms

    def test_total_duration_empty(self):
        assert _total_duration_ms([]) == 0.0

    def test_diff_shows_delta_pct(self):
        span_a = _make_span(start_ns=1_000_000_000, end_ns=1_100_000_000)  # 100ms
        span_b = _make_span(start_ns=1_000_000_000, end_ns=1_300_000_000)  # 300ms
        map_a = {"svc": [span_a]}
        map_b = {"svc": [span_b]}
        result = _diff_durations([span_a], [span_b], map_a, map_b)
        assert result["total_ms"]["a"] == 100.0
        assert result["total_ms"]["b"] == 300.0
        assert result["total_ms"]["delta_ms"] == 200.0
        assert result["total_ms"]["delta_pct"] == "+200.0%"


# ── Error Diff ──

class TestDiffErrors:
    """Test error span diffing."""

    def test_is_error_span_code_2(self):
        span = _make_span(status_code=2)
        assert _is_error_span(span) is True

    def test_is_not_error_span(self):
        span = _make_span(status_code=0)
        assert _is_error_span(span) is False

    def test_is_error_span_string_code(self):
        span = _make_span()
        span["status"] = {"code": "STATUS_CODE_ERROR"}
        assert _is_error_span(span) is True

    def test_errors_only_in_b(self):
        span_ok = _make_span(name="GET /ok", status_code=0)
        span_err = _make_span(name="POST /fail", status_code=2)
        result = _diff_errors([span_ok], [span_ok, span_err])
        assert result["a_error_count"] == 0
        assert result["b_error_count"] == 1
        assert len(result["errors_only_in_b"]) == 1
        assert result["errors_only_in_b"][0]["span_name"] == "POST /fail"

    def test_no_errors_in_either(self):
        span = _make_span(status_code=0)
        result = _diff_errors([span], [span])
        assert result["a_error_count"] == 0
        assert result["b_error_count"] == 0
        assert result["errors_only_in_a"] == []
        assert result["errors_only_in_b"] == []


# ── Attribute Diff ──

class TestDiffAttributes:
    """Test deep attribute-level diffing."""

    def test_same_attributes(self):
        attrs = [{"key": "http.method", "value": {"stringValue": "GET"}}]
        span_a = _make_span(attributes=attrs)
        span_b = _make_span(attributes=attrs)
        result = _diff_attributes([span_a], [span_b])
        assert result["a_only_keys"] == []
        assert result["b_only_keys"] == []
        assert result["value_differences"] == []

    def test_key_only_in_a(self):
        span_a = _make_span(
            attributes=[{"key": "http.method", "value": {"stringValue": "GET"}}]
        )
        span_b = _make_span(attributes=[])
        result = _diff_attributes([span_a], [span_b])
        assert "http.method" in result["a_only_keys"]

    def test_value_difference(self):
        span_a = _make_span(
            attributes=[{"key": "http.status_code", "value": {"intValue": 200}}]
        )
        span_b = _make_span(
            attributes=[{"key": "http.status_code", "value": {"intValue": 500}}]
        )
        result = _diff_attributes([span_a], [span_b])
        assert len(result["value_differences"]) == 1
        diff = result["value_differences"][0]
        assert diff["key"] == "http.status_code"
        assert "200" in diff["a_values"]
        assert "500" in diff["b_values"]


# ── Full diff_traces Integration ──

class TestDiffTraces:
    """Integration tests for the full diff_traces function."""

    def test_identical_traces_zero_delta(self):
        span = _make_span(name="GET /api", service="api")
        trace_a = _make_trace([span])
        trace_b = _make_trace([span])
        result = diff_traces(trace_a, trace_b, "aaa" * 8 + "bbbbbbbb", "ccc" * 8 + "dddddddd")

        assert result["trace_a"]["total_spans"] == 1
        assert result["trace_b"]["total_spans"] == 1
        assert result["structural_diff"]["services_only_in_a"] == []
        assert result["structural_diff"]["services_only_in_b"] == []
        assert result["span_count_diff"]["api"]["delta"] == 0
        assert result["duration_diff"]["total_ms"]["delta_ms"] == 0.0
        assert result["error_diff"]["a_error_count"] == 0
        assert result["error_diff"]["b_error_count"] == 0

    def test_extra_service_in_b(self):
        span_a = _make_span(service="api")
        span_b1 = _make_span(service="api")
        span_b2 = _make_span(service="db", span_id="bbb")
        trace_a = _make_trace([span_a])
        trace_b = _make_trace([span_b1, span_b2])
        result = diff_traces(trace_a, trace_b, "a" * 32, "b" * 32)

        assert "db" in result["structural_diff"]["services_only_in_b"]
        assert result["trace_b"]["total_spans"] == 2

    def test_empty_trace_a(self):
        trace_a = _make_trace([])
        span_b = _make_span(service="api")
        trace_b = _make_trace([span_b])
        result = diff_traces(trace_a, trace_b, "a" * 32, "b" * 32)

        assert result["trace_a"]["total_spans"] == 0
        assert result["trace_b"]["total_spans"] == 1
        assert result["structural_diff"]["services_only_in_b"] == ["api"]

    def test_both_empty_traces(self):
        result = diff_traces(
            _make_trace([]), _make_trace([]), "a" * 32, "b" * 32
        )
        assert result["trace_a"]["total_spans"] == 0
        assert result["trace_b"]["total_spans"] == 0
        assert result["structural_diff"]["services_in_both"] == []

    def test_different_error_counts(self):
        span_ok = _make_span(name="GET /ok", status_code=0, service="api")
        span_err = _make_span(
            name="POST /fail", status_code=2, service="api", span_id="err1"
        )
        trace_a = _make_trace([span_ok])
        trace_b = _make_trace([span_ok, span_err])
        result = diff_traces(trace_a, trace_b, "a" * 32, "b" * 32)

        assert result["trace_a"]["error_count"] == 0
        assert result["trace_b"]["error_count"] == 1
        assert result["error_diff"]["b_error_count"] == 1

    def test_service_name_extraction(self):
        span = _make_span(service="my-service")
        assert _get_service_name(span) == "my-service"

    def test_service_name_fallback_unknown(self):
        span = {"name": "test", "attributes": []}
        assert _get_service_name(span) == "unknown"
