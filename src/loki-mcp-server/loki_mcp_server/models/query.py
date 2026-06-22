"""Query result models for log and metric queries."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LokiLogEntry(BaseModel):
    """A single log entry from a Loki stream."""

    timestamp: str = Field(description="Nanosecond-precision timestamp string")
    line: str = Field(description="Log line content")


class LokiStream(BaseModel):
    """A log stream with its labels and entries."""

    labels: Dict[str, str] = Field(
        description="Stream labels (e.g., {'app': 'checkout', 'namespace': 'prod'})"
    )
    entries: List[LokiLogEntry] = Field(
        default_factory=list, description="Log entries in this stream"
    )


class LokiLogQueryResult(BaseModel):
    """Result from a LogQL log query (resultType: streams)."""

    streams: List[LokiStream] = Field(
        default_factory=list, description="Matching log streams"
    )
    direction: str = Field(
        default="backward", description="Query direction used"
    )
    limit: int = Field(default=1000, description="Limit applied to the query")
    stats: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional query statistics from Loki"
    )


class LokiMetricSample(BaseModel):
    """A single metric data point (timestamp, value)."""

    timestamp: float = Field(description="Unix timestamp (seconds)")
    value: str = Field(description="Metric value as string (Loki convention)")


class LokiMetricSeries(BaseModel):
    """A metric time series from a LogQL metric query."""

    metric: Dict[str, str] = Field(
        description="Metric labels identifying this series"
    )
    values: List[LokiMetricSample] = Field(
        default_factory=list, description="Time-series data points"
    )


class LokiMetricQueryResult(BaseModel):
    """Result from a LogQL metric query (resultType: matrix or vector)."""

    result_type: str = Field(
        description="Loki result type: 'matrix' or 'vector'"
    )
    series: List[LokiMetricSeries] = Field(
        default_factory=list, description="Metric time series"
    )
