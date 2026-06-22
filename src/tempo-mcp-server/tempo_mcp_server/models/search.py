"""Search-related Pydantic models.

Response fields validated against official Tempo /api/search response:
traceID, rootServiceName, rootTraceName, startTimeUnixNano, durationMs, spanSets.
"""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class TimeRangeInput(BaseTempoModel):
    """Normalized time range input supporting absolute and relative times."""

    start: Optional[float] = None   # Unix epoch seconds
    end: Optional[float] = None     # Unix epoch seconds
    since: Optional[str] = None     # Relative duration, e.g. "1h", "30m", "7d"


class SearchFilters(BaseTempoModel):
    """Normalized K8s-friendly search filters.

    These get translated to TraceQL predicates by the filter-to-TraceQL
    translation logic in utils/traceql_helpers.py.
    """

    # Service / K8s filters
    namespace: Optional[str] = None
    service: Optional[str] = None
    deployment: Optional[str] = None
    cluster: Optional[str] = None
    environment: Optional[str] = None

    # Status and performance
    status: Optional[str] = None              # "error", "ok", "unset"
    min_duration_ms: Optional[int] = None
    max_duration_ms: Optional[int] = None
    http_status_gte: Optional[int] = None
    span_name: Optional[str] = None

    # Structural filters (Tempo 2.10+)
    min_child_spans: Optional[int] = None
    max_child_spans: Optional[int] = None
    missing_attributes: Optional[List[str]] = None   # attr = nil
    present_attributes: Optional[List[str]] = None   # attr != nil
    leaf_spans_only: bool = False                     # span:childCount = 0


class TraceSearchResult(BaseTempoModel):
    """A single trace result from Tempo search."""

    trace_id: str
    root_service: Optional[str] = None
    root_span: Optional[str] = None
    start_time: Optional[str] = None         # ISO 8601 or epoch nanos
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    span_sets_count: int = 0
    matched_attributes: Optional[Dict[str, Any]] = None


class TraceSearchOutput(BaseTempoModel):
    """Output of tempo_traceql_search tool."""

    effective_query: str
    traces: List[TraceSearchResult]
    truncated: bool = False
    total_matched: Optional[int] = None
    determinism_note: str = (
        "Tempo search is non-deterministic. Results may differ between calls "
        "if the number of matching traces exceeds the limit."
    )
    metrics: Optional[Dict[str, Any]] = None
