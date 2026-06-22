"""Detected fields models for /loki/api/v1/detected_fields."""

from typing import List, Optional

from pydantic import BaseModel, Field


class LokiDetectedField(BaseModel):
    """A single field detected in log lines.

    Loki infers field names, types, cardinality, and the parser
    needed to extract them (json, logfmt, etc.).
    """

    label: str = Field(description="Field name (e.g., 'status_code', 'latency_ms')")
    type: str = Field(
        description="Inferred data type: string, int, float, boolean, duration, bytes"
    )
    cardinality: int = Field(
        description="Estimated number of unique values for this field"
    )
    parsers: List[str] = Field(
        default_factory=list,
        description="Parsers that can extract this field (e.g., ['json'], ['logfmt'])",
    )


class LokiDetectedFieldsResult(BaseModel):
    """Result from /loki/api/v1/detected_fields."""

    fields: List[LokiDetectedField] = Field(
        default_factory=list, description="Detected fields with type and cardinality"
    )
    limit: Optional[int] = Field(
        default=None, description="Limit applied to the detected fields query"
    )
