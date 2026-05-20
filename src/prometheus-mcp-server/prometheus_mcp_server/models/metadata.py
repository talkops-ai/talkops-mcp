"""Prometheus metric metadata models."""

from typing import Dict, List, Optional

from pydantic import Field

from prometheus_mcp_server.models.common import BasePrometheusModel


class MetricMetadata(BasePrometheusModel):
    """Metadata for a single metric from /api/v1/metadata."""

    name: str
    type: str  # counter, gauge, histogram, summary, unknown
    help: Optional[str] = None
    unit: Optional[str] = None


class MetricCatalog(BasePrometheusModel):
    """Catalog of all metric names with type and help text."""

    metrics: List[MetricMetadata] = Field(default_factory=list)
    total_count: int = 0


class RuntimeConfig(BasePrometheusModel):
    """Sanitized runtime configuration view."""

    global_config: Dict[str, str] = Field(
        default_factory=dict,
        description="Global settings: scrape_interval, evaluation_interval",
    )
    remote_write: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Remote write targets",
    )
    tsdb: Dict[str, object] = Field(
        default_factory=dict,
        description="TSDB stats: head_series, memory_bytes, retention",
    )


class CardinalityOverview(BasePrometheusModel):
    """TSDB cardinality overview."""

    total_series: int = 0
    head_series: int = 0
    num_label_pairs: int = 0
    memory_bytes: int = 0


class TopCardinalityMetric(BasePrometheusModel):
    """A high-cardinality metric entry."""

    metric_name: str
    series_count: int
    estimated_memory_bytes: Optional[int] = None


class CardinalitySummary(BasePrometheusModel):
    """Summarized TSDB status and top-N high-cardinality metrics."""

    overview: CardinalityOverview = Field(default_factory=CardinalityOverview)
    top_cardinality_metrics: List[TopCardinalityMetric] = Field(default_factory=list)
