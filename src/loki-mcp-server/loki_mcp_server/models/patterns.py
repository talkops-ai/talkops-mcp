"""Pattern detection models."""

from typing import Any, List

from pydantic import BaseModel, Field


class LokiPattern(BaseModel):
    """A detected log pattern with occurrence counts."""

    pattern: str = Field(description="The detected pattern string")
    total_count: int = Field(
        description="Total occurrences across all samples"
    )
    samples: List[List[Any]] = Field(
        default_factory=list,
        description="Time-series samples: [[timestamp, count], ...]",
    )


class LokiPatternResult(BaseModel):
    """Result from /loki/api/v1/patterns."""

    patterns: List[LokiPattern] = Field(
        default_factory=list, description="Detected log patterns"
    )
    total_patterns: int = Field(
        default=0, description="Total number of patterns detected"
    )
    suggested_parsers: List[str] = Field(
        default_factory=list,
        description="Auto-generated | pattern <...> expressions",
    )
