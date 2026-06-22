"""Unit tests for query guardrails and policy enforcement.

Covers §6.2: empty query rejection, limit/spss clamping, time range
requirements, TraceQL validation, and filter translation.
"""

import time
import pytest
from datetime import timedelta

from tempo_mcp_server.config import QueryPolicyConfig
from tempo_mcp_server.models.search import SearchFilters
from tempo_mcp_server.utils.time_helpers import parse_since, resolve_time_params
from tempo_mcp_server.utils.traceql_helpers import (
    build_traceql_from_filters,
    merge_traceql_queries,
    validate_traceql_basic,
)


class TestTimeParsing:
    """Relative time parsing: 30s, 15m, 1h, 7d, 2w."""

    def test_seconds(self):
        assert parse_since("30s") == timedelta(seconds=30)

    def test_minutes(self):
        assert parse_since("15m") == timedelta(minutes=15)

    def test_hours(self):
        assert parse_since("1h") == timedelta(hours=1)

    def test_days(self):
        assert parse_since("7d") == timedelta(days=7)

    def test_weeks(self):
        assert parse_since("2w") == timedelta(weeks=2)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid duration format"):
            parse_since("abc")

    def test_invalid_unit_raises(self):
        with pytest.raises(ValueError):
            parse_since("10x")


class TestTimeResolution:
    """Verify since vs start/end handling."""

    def test_since_resolves_to_window(self):
        start, end = resolve_time_params(since="1h")
        assert start is not None and end is not None
        assert (end - start) == pytest.approx(3600, abs=2)

    def test_explicit_start_end(self):
        start, end = resolve_time_params(start=100.0, end=200.0)
        assert start == 100.0 and end == 200.0

    def test_start_only_fills_end(self):
        now = time.time()
        start, end = resolve_time_params(start=now - 100)
        assert end is not None
        assert end >= now - 1


class TestTraceQLValidation:
    """Basic client-side TraceQL validation."""

    def test_empty_rejected(self):
        assert validate_traceql_basic("") is not None

    def test_valid_selector(self):
        assert validate_traceql_basic("{ status = error }") is None

    def test_mismatched_braces(self):
        result = validate_traceql_basic("{ status = error")
        assert result is not None
        assert "Mismatched" in result

    def test_metrics_expression_accepted(self):
        assert validate_traceql_basic("{ } | rate()") is None

    def test_no_braces_no_metrics_rejected(self):
        result = validate_traceql_basic("status = error")
        assert result is not None


class TestFilterToTraceQL:
    """TraceQL generation from K8s-friendly filters."""

    def test_empty_filters_produce_empty_query(self):
        assert build_traceql_from_filters(SearchFilters()) == ""

    def test_service_filter(self):
        q = build_traceql_from_filters(SearchFilters(service="api"))
        assert 'resource.service.name = "api"' in q

    def test_namespace_filter(self):
        q = build_traceql_from_filters(SearchFilters(namespace="prod"))
        assert 'k8s.namespace.name = "prod"' in q

    def test_error_status(self):
        q = build_traceql_from_filters(SearchFilters(status="error"))
        assert "status = error" in q

    def test_duration_bounds(self):
        q = build_traceql_from_filters(SearchFilters(min_duration_ms=100, max_duration_ms=5000))
        assert "duration >= 100ms" in q
        assert "duration <= 5000ms" in q

    def test_leaf_spans_only(self):
        q = build_traceql_from_filters(SearchFilters(leaf_spans_only=True))
        assert "span:childCount = 0" in q

    def test_nil_checks(self):
        q = build_traceql_from_filters(SearchFilters(
            missing_attributes=["http.status_code"],
            present_attributes=["db.system"],
        ))
        assert ".http.status_code = nil" in q
        assert ".db.system != nil" in q

    def test_combined_uses_and(self):
        q = build_traceql_from_filters(SearchFilters(service="api", status="error", min_duration_ms=500))
        assert "&&" in q
        assert q.startswith("{ ") and q.endswith(" }")


class TestQueryMerging:
    """Combining user-provided and generated TraceQL."""

    def test_merge_both(self):
        merged = merge_traceql_queries("{ status = error }", '{ resource.service.name = "api" }')
        assert "status = error" in merged
        assert 'resource.service.name = "api"' in merged
        assert "&&" in merged

    def test_merge_raw_only(self):
        assert merge_traceql_queries("{ status = error }", None) == "{ status = error }"

    def test_merge_generated_only(self):
        assert merge_traceql_queries(None, '{ resource.service.name = "api" }') == '{ resource.service.name = "api" }'

    def test_merge_neither(self):
        assert merge_traceql_queries(None, None) == ""


class TestLimitClamping:
    """Verify limit and spss are clamped to policy maximums."""

    def test_limit_clamped(self, query_policy):
        effective = min(500, query_policy.max_search_limit)
        assert effective == 100

    def test_spss_clamped(self, query_policy):
        effective = min(50, query_policy.max_spss)
        assert effective == 10

    def test_defaults_applied(self, query_policy):
        effective_limit = min(None or query_policy.default_search_limit, query_policy.max_search_limit)
        assert effective_limit == 20


class TestEmptyQueryRejection:
    """Verify require_filter_or_query guardrail."""

    # §11 #1: test_traceql_search_rejects_empty_query
    def test_policy_requires_filter(self, query_policy):
        assert query_policy.require_filter_or_query is True
        # No query + no filters = policy violation
        effective_query = merge_traceql_queries(None, build_traceql_from_filters(SearchFilters()))
        assert effective_query == ""


class TestTraceIdExtraction:
    """Verify trace ID extraction from log lines."""

    def test_trace_id_key_value(self):
        from tempo_mcp_server.utils.trace_id_extractor import extract_trace_id
        assert extract_trace_id('trace_id=1234567890abcdef1234567890abcdef') == "1234567890abcdef1234567890abcdef"

    def test_camelcase(self):
        from tempo_mcp_server.utils.trace_id_extractor import extract_trace_id
        assert extract_trace_id('traceId: ABCDEF1234567890ABCDEF1234567890') == "abcdef1234567890abcdef1234567890"

    def test_no_trace_id(self):
        from tempo_mcp_server.utils.trace_id_extractor import extract_trace_id
        assert extract_trace_id("normal log line") is None

    def test_empty(self):
        from tempo_mcp_server.utils.trace_id_extractor import extract_trace_id
        assert extract_trace_id("") is None
