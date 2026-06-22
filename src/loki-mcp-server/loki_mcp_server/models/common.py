"""Shared types, enums, and pagination models."""

from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
# Shared Literal Type Aliases
# ──────────────────────────────────────────────

QueryDirection = Literal["forward", "backward"]

# ──────────────────────────────────────────────
# Time Range
# ──────────────────────────────────────────────


class TimeRange(BaseModel):
    """Describes a query time window for Loki.

    Accepts RFC3339, RFC3339Nano, or numeric epoch strings.
    Relative expressions like 'now-1h' are resolved by the
    utils.time_utils module before being sent to Loki.
    """

    start: str = Field(
        ...,
        description=(
            "Start timestamp: RFC3339 string (e.g., '2024-01-01T00:00:00Z') "
            "or numeric epoch (seconds or nanoseconds)."
        ),
    )
    end: str = Field(
        ...,
        description=(
            "End timestamp: RFC3339 string (e.g., '2024-01-01T01:00:00Z') "
            "or numeric epoch (seconds or nanoseconds)."
        ),
    )


# ──────────────────────────────────────────────
# Pagination
# ──────────────────────────────────────────────

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Cursor-based pagination wrapper for list endpoints."""

    items: List[T] = Field(
        default_factory=list, description="Items in the current page"
    )
    total_count: int = Field(
        description="Total number of items across all pages"
    )
    next_cursor: Optional[str] = Field(
        default=None,
        description="Opaque cursor for the next page; null if this is the last page",
    )
    page_size: int = Field(description="Number of items per page")
