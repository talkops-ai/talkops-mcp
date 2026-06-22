"""Pydantic models for Tempo Operator CRD management.

Provides validated models for TempoStack and TempoMonolithic CRD summaries,
specs, and API response shapes.
"""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.common import BaseTempoModel


class TempoOperatorCRSummary(BaseTempoModel):
    """Summary of a Tempo Operator CR for list views."""

    name: str
    namespace: str
    kind: str  # "TempoStack" | "TempoMonolithic"
    storage_type: Optional[str] = None
    retention: Optional[str] = None
    size: Optional[str] = None
    status_phase: Optional[str] = None  # "Ready", "Pending", "Failed"
    ready: Optional[bool] = None
    age: Optional[str] = None  # Human-readable age


class TempoStackSpec(BaseTempoModel):
    """Validated TempoStack spec for CRD creation."""

    storage: Dict[str, Any]
    retention: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    search: Optional[Dict[str, Any]] = None
    tenants: Optional[Dict[str, Any]] = None
    template: Optional[Dict[str, Any]] = None


class TempoOperatorCRDetail(BaseTempoModel):
    """Full detail of a Tempo Operator CR."""

    name: str
    namespace: str
    kind: str
    api_version: str
    labels: Dict[str, str] = {}
    spec: Dict[str, Any] = {}
    status: Dict[str, Any] = {}
    conditions: List[Dict[str, Any]] = []
    storage_type: Optional[str] = None
    retention: Optional[str] = None
