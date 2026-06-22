"""TraceQL metrics models.

Response format validated against research: Tempo returns Prometheus-compatible
matrix format with status, data.resultType, data.result[].
"""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class MetricsPoint(BaseTempoModel):
    """A single time-series data point."""

    ts: float            # Unix timestamp
    value: str           # String value (Prometheus convention)


class MetricsSeries(BaseTempoModel):
    """A single time series with labels and data points."""

    labels: Dict[str, str] = {}
    points: List[MetricsPoint] = []
    summary: Optional[Dict[str, Any]] = None  # e.g. min, max, avg


class MetricsRangeOutput(BaseTempoModel):
    """Output of tempo_traceql_metrics_range tool."""

    effective_query: str
    result_type: str = "matrix"
    series: List[MetricsSeries] = []
    stats: Optional[Dict[str, Any]] = None
    sampling_applied: Optional[str] = None


class MetricsInstantOutput(BaseTempoModel):
    """Output of tempo_traceql_metrics_instant tool."""

    effective_query: str
    result_type: str = "vector"
    result: List[Dict[str, Any]] = []
    sampling_applied: Optional[str] = None
