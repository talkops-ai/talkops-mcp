"""Unit tests for trace summarization logic.

Covers §6.3: critical-path extraction, error-span prioritization,
headline generation, K8s context, and recommended queries.
"""

import pytest
from typing import Any, Dict

from tempo_mcp_server.utils.trace_summarizer import (
    summarize_trace,
    extract_critical_path,
    extract_error_spans,
    extract_k8s_context,
    generate_headline,
    _extract_spans,
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


class TestCriticalPathExtraction:
    """Verify critical path (longest-duration spans) extraction."""

    # §11 #4: test_summarize_trace_returns_critical_path
    def test_returns_critical_path(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        path = extract_critical_path(spans)
        assert len(path) >= 1
        # Longest span should be first
        assert path[0].duration_ms >= path[-1].duration_ms

    def test_empty_spans_returns_empty_path(self):
        assert extract_critical_path([]) == []


class TestErrorSpanExtraction:
    """Verify error detection from status codes and exception events."""

    def test_detects_error_status(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        errors = extract_error_spans(spans)
        assert len(errors) >= 1

    def test_extracts_exception_type(self, sample_trace_payload):
        spans = _extract_spans(sample_trace_payload)
        errors = extract_error_spans(spans)
        error = errors[0]
        assert error.error_type == "ConnectionError"
        assert error.message is not None
        assert "timeout" in error.message

    def test_prioritizes_error_spans(self, sample_trace_payload):
        """Only spans with status=error or exception events should appear."""
        spans = _extract_spans(sample_trace_payload)
        errors = extract_error_spans(spans)
        # Should NOT include the healthy GET /users span
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
        from tempo_mcp_server.models.trace import CriticalPathSpan
        critical = [CriticalPathSpan(service="api", span_name="GET", duration_ms=50, status="ok")]
        headline = generate_headline(critical, [], 50.0)
        assert "50ms" in headline
        assert "api/GET" in headline

    def test_headline_empty(self):
        headline = generate_headline([], [], 0)
        assert headline == "Trace summary"


class TestTraceSummarizeEndToEnd:
    """Full summarize_trace function tests."""

    def test_full_summary(self, sample_trace_payload):
        result = summarize_trace("test-id", sample_trace_payload)
        assert result.trace_id == "test-id"
        assert result.total_spans == 2
        assert result.total_services >= 1
        assert len(result.headline) > 0
        assert len(result.critical_path) >= 1
        assert len(result.errors) >= 1

    def test_suspected_root_cause(self, sample_trace_payload):
        result = summarize_trace("test-id", sample_trace_payload)
        assert result.suspected_root_cause is not None
        assert "ConnectionError" in result.suspected_root_cause

    def test_recommended_next_queries(self, sample_trace_payload):
        result = summarize_trace("test-id", sample_trace_payload)
        assert len(result.recommended_next_queries) >= 1
        # Should contain a service-specific TraceQL query
        assert any("service.name" in q for q in result.recommended_next_queries)

    def test_empty_trace_safe(self):
        result = summarize_trace("empty", {})
        assert result.total_spans == 0
        assert result.headline == "Trace summary"
        assert result.errors == []


class TestGapDetection:
    """Verify critical path vs wall-clock gap detection (Item #3)."""

    def _make_trace_with_gap(self) -> dict:
        """Build a trace with a 5ms critical path and a stray 7s async span.

        Root span: 0-5ms (GET /checkout)
        Child span: 1-4ms (DB query)
        Stray span: 7,000-7,004ms (dns.lookup — async/disjointed)
        Wall-clock: 7204ms, Critical path: 5+3 = 8ms → huge gap.
        """
        base_ns = 1700000000000000000  # arbitrary epoch in ns
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
                            "endTimeUnixNano": str(base_ns + 5_000_000),  # 5ms
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
                            "endTimeUnixNano": str(base_ns + 4_000_000),  # 3ms
                            "status": {"code": 0},
                            "attributes": [],
                            "events": [],
                        },
                        {
                            "traceId": "aaaa",
                            "spanId": "dns",
                            "parentSpanId": "",
                            "name": "dns.lookup",
                            "startTimeUnixNano": str(base_ns + 7_000_000_000),  # 7s later
                            "endTimeUnixNano": str(base_ns + 7_004_000_000),    # 7.004s
                            "status": {"code": 0},
                            "attributes": [],
                            "events": [],
                        },
                    ],
                }],
            }],
        }

    def test_detects_large_time_gap(self):
        """Async span 7s after a 5ms critical path → has_time_gaps=True."""
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        assert result.has_time_gaps is True
        assert result.time_gap_note is not None
        assert "wall-clock" in result.time_gap_note.lower()

    def test_gap_note_includes_ratio(self):
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        assert result.time_gap_note is not None
        assert "critical path" in result.time_gap_note.lower()
        # The note should mention the multiplier (×)
        assert "×" in result.time_gap_note

    def test_critical_path_duration_computed(self):
        """critical_path_duration_ms should be the sum of critical path span durations."""
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        expected_cp = sum(s.duration_ms for s in result.critical_path)
        assert result.critical_path_duration_ms == expected_cp
        # Critical path should be much smaller than wall-clock
        assert result.critical_path_duration_ms < result.total_duration_ms * 0.5

    def test_headline_disambiguates_when_gap(self):
        """Headline should show 'wall-clock (Xms critical path)' when gaps detected."""
        result = summarize_trace("gap-trace", self._make_trace_with_gap())
        assert "wall-clock" in result.headline
        assert "critical path" in result.headline

    def test_no_gap_for_contiguous_trace(self, sample_trace_payload):
        """Normal contiguous trace should NOT trigger gap detection."""
        result = summarize_trace("normal", sample_trace_payload)
        assert result.has_time_gaps is False
        assert result.time_gap_note is None
        # Headline should use "total" format, not "wall-clock"
        assert "total" in result.headline
        assert "wall-clock" not in result.headline

    def test_critical_path_duration_on_contiguous_trace(self, sample_trace_payload):
        """critical_path_duration_ms is populated even on contiguous traces."""
        result = summarize_trace("normal", sample_trace_payload)
        assert result.critical_path_duration_ms > 0

    def test_empty_trace_no_gap(self):
        """Empty trace should have has_time_gaps=False."""
        result = summarize_trace("empty", {})
        assert result.has_time_gaps is False
        assert result.time_gap_note is None
        assert result.critical_path_duration_ms == 0.0

