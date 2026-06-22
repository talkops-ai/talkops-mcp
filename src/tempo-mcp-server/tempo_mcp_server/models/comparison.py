"""Pydantic models for trace comparison output.

Provides validated models for the multi-dimensional diff produced by
tempo_compare_traces.
"""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class TraceBrief(BaseTempoModel):
    """Brief summary of one trace in a comparison."""

    trace_id: str
    total_spans: int
    services: List[str]
    duration_ms: float
    error_count: int


class TraceComparisonResult(BaseTempoModel):
    """Full output of tempo_compare_traces."""

    trace_a: TraceBrief
    trace_b: TraceBrief
    structural_diff: Dict[str, Any]
    span_count_diff: Dict[str, Any]
    duration_diff: Dict[str, Any]
    error_diff: Dict[str, Any]
    attribute_diff: Optional[Dict[str, Any]] = None
