"""Pydantic models for metric cardinality analysis."""

from typing import List, Optional

from pydantic import BaseModel, Field


class MetricCardinalityIssue(BaseModel):
    """A single metric cardinality issue detected by governance tools."""

    metric_name: str = Field(description="Metric name with high cardinality")
    estimated_series: int = Field(
        description="Estimated active time series count"
    )
    high_cardinality_labels: List[str] = Field(
        default_factory=list,
        description="Labels contributing most to cardinality",
    )
    source: str = Field(
        default="unknown",
        description="Source of the metric (spanmetrics, application, collector)",
    )
    recommendation: str = Field(
        default="",
        description="Recommended remediation (e.g., 'drop label via transform processor')",
    )
    severity: str = Field(
        default="warning",
        description="Issue severity: info, warning, critical",
    )


class CardinalityReport(BaseModel):
    """Aggregate cardinality analysis report.

    Used by ``otel_detect_cardinality`` tool.
    """

    collector_name: Optional[str] = Field(
        default=None, description="Collector CRD name if scoped"
    )
    namespace: Optional[str] = Field(
        default=None, description="Namespace if scoped"
    )

    total_estimated_series: int = Field(
        default=0,
        description="Total estimated active series across all metrics",
    )
    issues: List[MetricCardinalityIssue] = Field(
        default_factory=list,
        description="Individual cardinality issues found",
    )
    total_issues: int = Field(
        default=0,
        description="Total number of cardinality issues",
    )

    # Generated remediation
    transform_processor_yaml: Optional[str] = Field(
        default=None,
        description="Generated transform processor YAML to drop high-cardinality attributes",
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="Analysis warnings",
    )
