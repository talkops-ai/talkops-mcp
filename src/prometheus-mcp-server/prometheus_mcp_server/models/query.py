"""PromQL query result models."""

from typing import Dict, List, Literal, Optional, Tuple

from pydantic import Field

from prometheus_mcp_server.models.common import BasePrometheusModel


class ValidatePromQLResult(BasePrometheusModel):
    """Result of PromQL validation."""

    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class InstantSample(BasePrometheusModel):
    """A single sample from an instant query result."""

    metric: Dict[str, str] = Field(default_factory=dict)
    value: Tuple[float, str]


class InstantQueryResult(BasePrometheusModel):
    """Result of a PromQL instant query."""

    resultType: Literal["vector", "scalar", "string", "matrix"] = "vector"
    result: List[InstantSample] = Field(default_factory=list)
    eval_time_seconds: Optional[float] = None
    sample_count: Optional[int] = None


class RangeSeries(BasePrometheusModel):
    """A single time series from a range query result."""

    metric: Dict[str, str] = Field(default_factory=dict)
    values: List[Tuple[float, str]] = Field(default_factory=list)


class DownsamplingMetadata(BasePrometheusModel):
    """Metadata about downsampling applied to range query results."""

    strategy: str = "average"
    original_step: str = ""
    effective_step: str = ""
    max_points_per_series: int = 200
    original_point_count: Optional[int] = None
    downsampled_point_count: Optional[int] = None


class RangeQueryResult(BasePrometheusModel):
    """Result of a safe PromQL range query with downsampling."""

    series: List[RangeSeries] = Field(default_factory=list)
    downsampling: DownsamplingMetadata = Field(default_factory=DownsamplingMetadata)


class LabelTopologyResult(BasePrometheusModel):
    """Result of label topology exploration for a metric."""

    metric_name: str
    label_names: List[str] = Field(default_factory=list)
    label_values: Dict[str, List[str]] = Field(default_factory=dict)
