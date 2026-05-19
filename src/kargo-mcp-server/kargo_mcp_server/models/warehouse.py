"""Kargo Warehouse models."""


from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from kargo_mcp_server.models.common import ObjectMeta


class WarehouseSource(BaseModel):
    """Artifact source subscription within a Warehouse."""

    type: str  # "git", "image", "helm"
    url: str
    selector: Optional[str] = None


class WarehouseSpec(BaseModel):
    """Warehouse specification."""

    sources: List[WarehouseSource] = Field(default_factory=list)


class WarehouseStatus(BaseModel):
    """Warehouse status."""

    last_sync_time: Optional[datetime] = Field(default=None, alias="lastSyncTime")
    conditions: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class Warehouse(BaseModel):
    """Full Kargo Warehouse resource."""

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Warehouse"
    metadata: ObjectMeta
    spec: WarehouseSpec = Field(default_factory=WarehouseSpec)
    status: Optional[WarehouseStatus] = None


class WarehouseSummary(BaseModel):
    """Compact warehouse summary."""

    name: str
    source_types: List[str] = Field(default_factory=list)
