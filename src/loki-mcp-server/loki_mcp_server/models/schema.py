"""Schema and cardinality analysis models."""

from typing import Dict, List

from pydantic import BaseModel, Field


class LokiLabelCardinality(BaseModel):
    """Cardinality info for a single label."""

    label: str = Field(description="Label name")
    unique_values: int = Field(description="Number of unique values")
    is_high_cardinality: bool = Field(
        description="True if unique_values exceeds the configured threshold"
    )


class LokiCardinalityReport(BaseModel):
    """Full cardinality report for a label matcher."""

    matcher: str = Field(description="The LogQL label matcher analyzed")
    total_series: int = Field(description="Total number of matching series")
    labels: List[LokiLabelCardinality] = Field(
        default_factory=list,
        description="Per-label cardinality breakdown",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about high-cardinality labels",
    )


class LokiSeriesInfo(BaseModel):
    """A single series with its label-value combinations."""

    labels: Dict[str, str] = Field(
        description="Label-value map for this series"
    )
