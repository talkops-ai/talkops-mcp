"""Shared types, enums, and pagination models."""

from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
# Shared Literal Type Aliases
# ──────────────────────────────────────────────

SignalType = Literal["traces", "metrics", "logs"]
CollectorMode = Literal["deployment", "daemonset", "statefulset", "sidecar"]
StabilityLevel = Literal["stable", "beta", "alpha", "development", "not_supported"]
SamplingMode = Literal["head", "tail", "none"]
DetailLevel = Literal["summary", "full"]


# ──────────────────────────────────────────────
# Pagination
# ──────────────────────────────────────────────

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Cursor-based pagination wrapper for list endpoints."""

    items: List[T] = Field(default_factory=list, description="Items in the current page")
    total_count: int = Field(description="Total number of items across all pages")
    next_cursor: Optional[str] = Field(
        default=None,
        description="Opaque cursor for the next page; null if this is the last page",
    )
    page_size: int = Field(description="Number of items per page")


# ──────────────────────────────────────────────
# Shared component reference models
# ──────────────────────────────────────────────


class ComponentRef(BaseModel):
    """Reference to a collector pipeline component (receiver, processor, exporter)."""

    name: str = Field(description="Component instance name from the config YAML key")
    type: str = Field(
        description="Component type (e.g., 'otlp', 'batch', 'k8sattributes')"
    )
