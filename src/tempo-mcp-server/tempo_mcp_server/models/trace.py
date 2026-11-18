"""Trace retrieval and summarization models (facts-only)."""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class GetTraceOutput(BaseTempoModel):
    """Output of tempo_get_trace tool."""

    trace_id: str
    format: str = "llm"  # "llm" or "otlp_json"
    trace: Dict[str, Any] = {}
    truncated: bool = False
    llm_format_used: bool = True


class CriticalPathSpan(BaseTempoModel):
    """A span on the critical path or self-time hotspot list of a trace."""

    service: str
    span_name: str
    duration_ms: float
    self_time_ms: Optional[float] = None
    status: str = "ok"
    reason: Optional[str] = None


class TraceErrorSummary(BaseTempoModel):
    """Summary of an error span found in a trace."""

    service: str
    span_name: str
    error_type: Optional[str] = None
    message: Optional[str] = None
    span_id: Optional[str] = None
    depth: Optional[int] = None


class TraceSummaryOutput(BaseTempoModel):
    """Output of tempo_summarize_trace tool — factual server-side aggregation."""

    trace_id: str
    headline: str
    total_spans: int = 0
    total_services: int = 0
    total_duration_ms: float = 0.0
    critical_path_duration_ms: float = 0.0
    has_time_gaps: bool = False
    time_gap_note: Optional[str] = None
    critical_path: List[CriticalPathSpan] = []
    self_time_hotspots: List[CriticalPathSpan] = []
    errors: List[TraceErrorSummary] = []
    deepest_error_span: Optional[TraceErrorSummary] = None
    error_origin_service: Optional[str] = None
    k8s_context: Optional[Dict[str, Any]] = None
    observation_codes: List[str] = []
