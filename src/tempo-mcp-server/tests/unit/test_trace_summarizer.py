"""Unit tests for trace summarization logic.

Covers critical-path extraction, self-time hotspots, deepest error span,
error origin service, observation codes, K8s context, and time-gap facts.
"""

import pytest

from tempo_mcp_server.models.diagnostics import ALL_OBSERVATION_CODES
from tempo_mcp_server.models.trace import CriticalPathSpan
from tempo_mcp_server.utils.trace_summarizer import (
    _extract_spans,
    extract_critical_path,
    extract_error_spans,
    extract_k8s_context,
    extract_self_time_hotspots,
    generate_headline,
    summarize_trace,
)


class TestSpanExtraction:
    """Verify spans are correctly flattened from OTLP format."""

    def test_extracts_spans_from_otlp(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        assert len(spans) == 2

    def test_extracts_from_empty_trace(self):
        assert _extract_spans({}) == []

    def test_extracts_from_flat_list(self):
        spans = _extract_spans([{"name": "a"}, {"name": "b"}])  # type: ignore[arg-type]
        assert len(spans) == 2


class TestCriticalPathAndSelfTimeExtraction:
    """Verify critical path and self-time hotspot extraction."""

    def test_returns_critical_path(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        path = extract_critical_path(spans)
        assert len(path) >= 1
        assert path[0].duration_ms >= path[-1].duration_ms
        assert path[0].self_time_ms is not None
        assert path[0].self_time_ms >= 0.0

    def test_returns_self_time_hotspots(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        hotspots = extract_self_time_hotspots(spans)
        assert len(hotspots) >= 1
        assert hotspots[0].self_time_ms is not None
        assert hotspots[-1].self_time_ms is not None
        assert hotspots[0].self_time_ms >= hotspots[-1].self_time_ms

    def test_empty_spans_returns_empty_path(self):
        assert extract_critical_path([]) == []
        assert extract_self_time_hotspots([]) == []


class TestErrorSpanExtraction:
    """Verify error detection from status codes, exception events, and depth."""

    def test_detects_error_status(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        errors = extract_error_spans(spans)
        assert len(errors) >= 1

    def test_extracts_exception_type_and_depth(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        errors = extract_error_spans(spans)
        error = errors[0]
        assert error.error_type == "ConnectionError"
        assert error.message is not None
        assert "timeout" in error.message
        assert error.depth is not None
        assert error.depth >= 0

    def test_prioritizes_error_spans(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        errors = extract_error_spans(spans)
        error_names = [e.span_name for e in errors]
        assert "GET /users" not in error_names
        assert "SELECT users" in error_names


class TestK8sContextExtraction:
    """Verify K8s resource attributes are pulled from trace spans."""

    def test_extracts_namespace(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        ctx = extract_k8s_context(spans)
        assert ctx.get("k8s.namespace.name") == "production"

    def test_extracts_services(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        ctx = extract_k8s_context(spans)
        assert "services" in ctx
        assert "api-gateway" in ctx["services"]


class TestHeadlineGeneration:
    """Verify one-line trace summary headline."""

    def test_headline_with_errors(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        critical = extract_critical_path(spans)
        errors = extract_error_spans(spans)
        headline = generate_headline(critical, errors, 150.0)
        assert "150ms" in headline
        assert "error" in headline.lower()

    def test_headline_no_errors(self):
        critical = [CriticalPathSpan(service="api", span_name="GET", duration_ms=50, status="ok")]
        headline = generate_headline(critical, [], 50.0)
        assert "50ms" in headline
        assert "api/GET" in headline

    def test_headline_empty(self):
        headline = generate_headline([], [], 0)
        assert headline == "Trace summary"


class TestTraceSummarizeEndToEnd:
    """Full summarize_trace function tests (facts-only boundary)."""

    def test_full_summary(self, sample_trace_payload):
        result = summarize_trace("test-id", sample_trace_payload)
        assert result.trace_id == "test-id"
        assert result.total_spans == 2
        assert result.total_services >= 1
        assert len(result.headline) > 0
        assert len(result.critical_path) >= 1
        assert len(result.self_time_hotspots) >= 1
        assert len(result.errors) >= 1

    def test_deepest_error_span_and_origin_service(self, sample_trace_payload):
        result = summarize_trace("test-id", sample_trace_payload)
        assert result.deepest_error_span is not None
        assert result.deepest_error_span.span_name == "SELECT users"
        assert result.error_origin_service is not None
        assert "SPAN_ERRORS_PRESENT" in result.observation_codes
        for code in result.observation_codes:
            assert code in ALL_OBSERVATION_CODES

    def test_facts_only_boundary_no_root_cause_or_next_queries(self, sample_trace_payload):
        result = summarize_trace("test-id", sample_trace_payload)
        dumped = result.model_dump()
        assert "suspected_root_cause" not in dumped
        assert "recommended_next_queries" not in dumped

    def test_empty_trace_safe(self):
        result = summarize_trace("empty", {})
        assert result.total_spans == 0
        assert result.headline == "Trace summary"
        assert result.errors == []
        assert result.deepest_error_span is None
        assert result.error_origin_service is None
        assert result.observation_codes == []


class TestGapDetection:
    """Verify critical path vs wall-clock gap detection."""

    def _make_trace_with_gap(self) -> dict:
        base_ns = 1700000000000000000
        return {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout"}},
                    ],
                },
                "scopeSpans": [{
                    "spans": [
                        {
                            "traceId": "aaaa",
                            "spanId": "root",
                            "parentSpanId": "",
                            "name": "GET /checkout",
                            "startTimeUnixNano": str(base_ns),
                            "endTimeUnixNano": str(base_ns + 5_000_000),
                            "status": {"code": 0},
                            "attributes": [],
                            "events": [],
                        },
                        {
                            "traceId": "aaaa",
                            "spanId": "db",
                            "parentSpanId": "root",
                            "name": "SELECT orders",
                            "startTimeUnixNano": str(base_ns + 1_000_000),
                            "endTimeUnixNano": str(base_ns + 4_000_000),
                            "status": {"code": 0},
                            "attributes": [],
                            "events": [],
                        },
                        {
                            "traceId": "aaaa",
                            "spanId": "dns",
                            "parentSpanId": "",
                            "name": "dns.lookup",
                            "startTimeUnixNano": str(base_ns + 7_000_000_000),
                            "endTimeUnixNano": str(base_ns + 7_004_000_000),
                            "status": {"code": 0},
                            "attributes": [],
                            "events": [],
                        },
                    ],
                }],
            }],
        }

    def test_detects_large_time_gap(self):
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        assert result.has_time_gaps is True
        assert result.time_gap_note is not None
        assert "wall-clock" in result.time_gap_note.lower()
        assert "TRACE_TIME_GAPS" in result.observation_codes

    def test_gap_note_includes_ratio(self):
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        assert result.time_gap_note is not None
        assert "critical path" in result.time_gap_note.lower()
        assert "x" in result.time_gap_note

    def test_critical_path_duration_computed(self):
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        expected_cp = sum(s.duration_ms for s in result.critical_path)
        assert result.critical_path_duration_ms == expected_cp
        assert result.critical_path_duration_ms < result.total_duration_ms * 0.5

    def test_headline_disambiguates_when_gap(self):
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        assert "wall-clock" in result.headline
        assert "critical path" in result.headline

    def test_no_gap_for_contiguous_trace(self, sample_trace_payload):
        result = summarize_trace("normal", sample_trace_payload)
        assert result.has_time_gaps is False
        assert result.time_gap_note is None
        assert "total" in result.headline
        assert "wall-clock" not in result.headline

    def test_critical_path_duration_on_contiguous_trace(self, sample_trace_payload):
        result = summarize_trace("normal", sample_trace_payload)
        assert result.critical_path_duration_ms > 0

    def test_empty_trace_no_gap(self):
        result = summarize_trace("empty", {})
        assert result.has_time_gaps is False
        assert result.time_gap_note is None
        assert result.critical_path_duration_ms == 0.0
