"""Search-related Pydantic models.

Response fields validated against official Tempo /api/search response:
traceID, rootServiceName, rootTraceName, startTimeUnixNano, durationMs, spanSets.
"""

from typing import Any, Dict, List, Optional

from pydantic import model_validator

from tempo_mcp_server.models.common import BaseTempoModel
from tempo_mcp_server.utils.time_helpers import duration_to_seconds


class TimeRangeInput(BaseTempoModel):
    """Normalized time range input supporting absolute and relative times."""

    start: Optional[float] = None   # Unix epoch seconds
    end: Optional[float] = None     # Unix epoch seconds
    since: Optional[str] = None     # Relative duration, e.g. "1h", "30m", "7d"


class SearchFilters(BaseTempoModel):
    """Normalized K8s-friendly search filters.

    Translated to TraceQL predicates by utils/traceql_helpers.py.
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

    @model_validator(mode="before")
    @classmethod
    def _normalize_filter_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "service_name" in out and not out.get("service"):
            out["service"] = out.pop("service_name")
        else:
            out.pop("service_name", None)
        for str_key, ms_key in (("min_duration", "min_duration_ms"), ("max_duration", "max_duration_ms")):
            raw_dur = out.pop(str_key, None)
            if raw_dur is not None and out.get(ms_key) is None:
                try:
                    out[ms_key] = int(duration_to_seconds(str(raw_dur)) * 1000)
                except Exception:
                    pass
        return out


class TraceSearchResult(BaseTempoModel):
    """A single trace result from Tempo search (compact 5-field summary + resource_uri)."""

    trace_id: str
    root_service: Optional[str] = None
    root_span: Optional[str] = None
    start_time: Optional[str] = None         # ISO 8601 or epoch nanos
    duration_ms: Optional[int] = None
    status: Optional[str] = None
    span_sets_count: int = 0
    matched_attributes: Optional[Dict[str, Any]] = None
    resource_uri: Optional[str] = None


class TraceSearchOutput(BaseTempoModel):
    """Output of tempo_traceql_search tool."""

    effective_query: str
    traces: List[TraceSearchResult]
    truncated: bool = False
    total_matched: Optional[int] = None
    next_window: Optional[Dict[str, float]] = None
    determinism_note: str = (
        "Tempo search is non-deterministic when matching traces exceed limit."
    )
    metrics: Optional[Dict[str, Any]] = None
