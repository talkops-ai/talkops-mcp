"""Kargo Warehouse models (Kargo v1.10–v1.12)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from kargo_mcp_server.models.common import ObjectMeta


class FreightCreationCriteria(BaseModel):
    """Criteria expression evaluated before auto-creating Freight (Kargo v1.8+)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    expression: Optional[str] = None


class WarehouseSpec(BaseModel):
    """Warehouse specification."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    interval: Optional[str] = "5m0s"
    shard: Optional[str] = None
    freight_creation_policy: str = Field(
        default="Automatic", alias="freightCreationPolicy"
    )
    freight_creation_criteria: Optional[FreightCreationCriteria] = Field(
        default=None, alias="freightCreationCriteria"
    )
    subscriptions: List[Dict[str, Any]] = Field(default_factory=list)


class WarehouseStatus(BaseModel):
    """Warehouse status including discoveredArtifacts and conditions."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    last_handled_refresh: Optional[str] = Field(
        default=None, alias="lastHandledRefresh"
    )
    last_freight_id: Optional[str] = Field(default=None, alias="lastFreightID")
    discovered_artifacts: Optional[Dict[str, Any]] = Field(
        default=None, alias="discoveredArtifacts"
    )
    observed_generation: Optional[int] = Field(
        default=None, alias="observedGeneration"
    )


class Warehouse(BaseModel):
    """Full Kargo Warehouse resource."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Warehouse"
    metadata: ObjectMeta
    spec: WarehouseSpec = Field(default_factory=WarehouseSpec)
    status: Optional[WarehouseStatus] = None

    def get_subscription_types(self) -> List[str]:
        types = set()
        for sub in self.spec.subscriptions:
            if isinstance(sub, dict):
                for k in ("git", "image", "chart"):
                    if k in sub:
                        types.add(k)
                for k in sub:
                    if k not in ("git", "image", "chart", "name"):
                        types.add(k)
        return sorted(types)

    def is_ready(self) -> bool:
        if not self.status or not self.status.conditions:
            return True
        for cond in self.status.conditions:
            if cond.get("type") in ("Ready", "Healthy"):
                return cond.get("status") == "True"
        return True


class WarehouseSummary(BaseModel):
    """Compact warehouse summary."""

    name: str
    namespace: str = ""
    subscription_types: List[str] = Field(default_factory=list)
    subscriptions_count: int = 0
    freight_creation_policy: str = "Automatic"
    interval: str = "5m0s"
    ready: bool = True
    last_freight_id: Optional[str] = None
