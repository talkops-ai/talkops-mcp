"""Trace retrieval and summarization models."""

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
    """A span on the critical path of a trace."""

    service: str
    span_name: str
    duration_ms: float
    status: str = "ok"
    reason: Optional[str] = None  # Why this is on the critical path


class TraceErrorSummary(BaseTempoModel):
    """Summary of an error found in a trace."""

    service: str
    span_name: str
    error_type: Optional[str] = None
    message: Optional[str] = None
    span_id: Optional[str] = None


class TraceSummaryOutput(BaseTempoModel):
    """Output of tempo_summarize_trace tool — server-side intelligence."""

    trace_id: str
    headline: str                                     # One-line summary
    total_spans: int = 0
    total_services: int = 0
    total_duration_ms: float = 0.0                    # Wall-clock: max(end) - min(start)
    critical_path_duration_ms: float = 0.0            # Sum of critical path span durations
    has_time_gaps: bool = False                        # True if wall-clock >> critical path
    time_gap_note: Optional[str] = None               # Explanation when gaps detected
    critical_path: List[CriticalPathSpan] = []
    errors: List[TraceErrorSummary] = []
    k8s_context: Optional[Dict[str, Any]] = None      # Extracted K8s attributes
    suspected_root_cause: Optional[str] = None
    recommended_next_queries: List[str] = []

