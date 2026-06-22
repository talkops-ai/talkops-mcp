"""Cross-pillar pivot models."""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class ExemplarTraceCandidate(BaseTempoModel):
    """A trace candidate resolved from an exemplar."""

    trace_id: str
    source: str = "exemplar"       # "exemplar", "log", "metric"
    timestamp: Optional[float] = None
    summary: Optional[str] = None


class ExemplarTracesOutput(BaseTempoModel):
    """Output of tempo_get_exemplar_traces tool."""

    trace_candidates: List[ExemplarTraceCandidate] = []
    total: int = 0


class TraceFromLogOutput(BaseTempoModel):
    """Output of tempo_get_trace_from_log tool."""

    extracted_trace_id: Optional[str] = None
    resolved_from: str = "log_line"  # "log_line", "user_input"
    trace_summary: Optional[Dict[str, Any]] = None
    trace: Optional[Dict[str, Any]] = None
