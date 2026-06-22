"""Pydantic models for SpanMetrics connector profiles.

Represents the ``spanmetrics`` connector configuration extracted from
an OpenTelemetryCollector config, corresponding to the
``otel://spanmetrics/{namespace}/{collector}`` resource.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class HistogramBucketConfig(BaseModel):
    """Histogram bucket configuration for spanmetrics."""

    type: str = Field(
        default="explicit",
        description="Bucket type: 'explicit' or 'exponential'",
    )
    explicit_buckets: Optional[List[float]] = Field(
        default=None,
        description="Explicit histogram bucket boundaries in milliseconds",
    )
    max_size: Optional[int] = Field(
        default=None,
        description="Max size for exponential histogram buckets",
    )

    @field_validator("explicit_buckets", mode="before")
    @classmethod
    def _parse_duration_buckets(
        cls, v: Optional[List[Union[str, int, float]]],
    ) -> Optional[List[float]]:
        """Coerce OTel duration strings to float ms values.

        Handles inputs like ``["2ms", "1s", 100, "15s"]`` by converting
        each element through :func:`parse_duration_to_ms`.
        """
        if v is None:
            return v
        from opentelemetry_mcp_server.utils.duration import parse_duration_to_ms

        return [parse_duration_to_ms(b) for b in v]


class SpanMetricsProfile(BaseModel):
    """SpanMetrics connector configuration profile.

    Corresponds to the ``otel://spanmetrics/{namespace}/{collector}`` resource.
    """

    collector_name: str = Field(description="Parent collector CRD name")
    collector_namespace: str = Field(description="Parent collector namespace")
    enabled: bool = Field(
        default=False,
        description="Whether spanmetrics connector is configured",
    )

    # Dimensions
    dimensions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Custom dimensions added to span metrics (name + optional default)",
    )
    exclude_dimensions: List[str] = Field(
        default_factory=list,
        description="Dimensions excluded from span metrics",
    )

    # Histogram config
    histogram: HistogramBucketConfig = Field(
        default_factory=HistogramBucketConfig,
        description="Histogram bucket configuration",
    )

    # Metric naming
    namespace: Optional[str] = Field(
        default=None,
        description="Metric namespace prefix (e.g., 'span.metrics')",
    )
    metrics_flush_interval: Optional[str] = Field(
        default=None,
        description="Flush interval (e.g., '15s', '30s')",
    )

    # Pipeline wiring
    source_pipeline: Optional[str] = Field(
        default=None,
        description="Traces pipeline that feeds into the spanmetrics connector",
    )
    target_pipeline: Optional[str] = Field(
        default=None,
        description="Metrics pipeline that receives spanmetrics output",
    )

    # Cardinality estimation
    estimated_series_per_service: Optional[int] = Field(
        default=None,
        description="Estimated metric series count per service based on dimensions",
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Configuration warnings (e.g., high cardinality risk)",
    )
