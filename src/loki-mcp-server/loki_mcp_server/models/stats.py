"""Index statistics models."""

from pydantic import BaseModel, Field


class LokiIndexStats(BaseModel):
    """Index statistics from /loki/api/v1/index/stats.

    Shows how many streams, chunks, entries, and bytes a query
    would touch — used for cost-aware query gating.
    """

    streams: int = Field(description="Number of matching streams")
    chunks: int = Field(description="Number of chunks to scan")
    entries: int = Field(description="Number of log entries")
    bytes: int = Field(description="Total bytes to scan")
