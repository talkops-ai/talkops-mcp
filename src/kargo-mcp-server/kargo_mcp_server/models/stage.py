"""Kargo Stage models (Kargo v1.10–v1.12)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from kargo_mcp_server.models.common import ObjectMeta


class RequestedFreightOrigin(BaseModel):
    """Origin of requested freight (must be a Warehouse)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kind: str = "Warehouse"
    name: str


class AutoPromotionOptions(BaseModel):
    """Auto-promotion selection policy options (Kargo v1.8+)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    selection_policy: Optional[str] = Field(
        default=None, alias="selectionPolicy"
    )  # "NewestFreight" | "MatchUpstream"


class FreightSources(BaseModel):
    """Specifies where requested Freight may be obtained from."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    direct: bool = False
    stages: List[str] = Field(default_factory=list)
    availability_strategy: Optional[str] = Field(
        default=None, alias="availabilityStrategy"
    )  # "OneOf" | "All"
    required_soak_time: Optional[str] = Field(
        default=None, alias="requiredSoakTime"
    )
    auto_promotion_options: Optional[AutoPromotionOptions] = Field(
        default=None, alias="autoPromotionOptions"
    )


class RequestedFreight(BaseModel):
    """Freight request entry within a Stage spec."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    origin: RequestedFreightOrigin
    sources: FreightSources = Field(default_factory=FreightSources)


class StageSpec(BaseModel):
    """Stage specification (Kargo v1.12)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    shard: Optional[str] = None
    vars: List[Dict[str, Any]] = Field(default_factory=list)
    requested_freight: List[RequestedFreight] = Field(
        default_factory=list, alias="requestedFreight"
    )
    promotion_template: Optional[Dict[str, Any]] = Field(
        default=None, alias="promotionTemplate"
    )
    verification: Optional[Dict[str, Any]] = None


class StageStatus(BaseModel):
    """Stage status (Kargo v1.12)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    freight_history: List[Dict[str, Any]] = Field(
        default_factory=list, alias="freightHistory"
    )
    freight_summary: Optional[str] = Field(default=None, alias="freightSummary")
    health: Optional[Dict[str, Any]] = None
    current_promotion: Optional[Dict[str, Any]] = Field(
        default=None, alias="currentPromotion"
    )
    last_promotion: Optional[Dict[str, Any]] = Field(
        default=None, alias="lastPromotion"
    )
    auto_promotion_enabled: Optional[bool] = Field(
        default=None, alias="autoPromotionEnabled"
    )
    auto_promotion_holds: List[Dict[str, Any]] = Field(
        default_factory=list, alias="autoPromotionHolds"
    )
    effective_auto_promotion_holds: List[Dict[str, Any]] = Field(
        default_factory=list, alias="effectiveAutoPromotionHolds"
    )
    last_handled_refresh: Optional[str] = Field(
        default=None, alias="lastHandledRefresh"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Legacy fallback fields
    current_freight_id: Optional[str] = Field(default=None, alias="currentFreightId")
    last_promotion_id: Optional[str] = Field(default=None, alias="lastPromotionId")

    @field_validator("auto_promotion_holds", "effective_auto_promotion_holds", mode="before")
    @classmethod
    def _normalize_holds(cls, val: Any) -> List[Dict[str, Any]]:
        """Normalize Kargo v1.12 map-shaped autoPromotionHolds into a list of dicts."""
        if val is None:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            normalized: List[Dict[str, Any]] = []
            for key, entry in val.items():
                if isinstance(entry, dict):
                    item: Dict[str, Any] = {"holdKey": str(key), **entry}
                    origin_val = item.get("origin")
                    if isinstance(origin_val, dict) and origin_val.get("name"):
                        item["originName"] = str(origin_val["name"])
                    elif not origin_val and "/" in str(key):
                        item["originName"] = str(key).split("/", 1)[1]
                    normalized.append(item)
                else:
                    origin_name = str(key).split("/", 1)[1] if "/" in str(key) else str(key)
                    normalized.append({"holdKey": str(key), "origin": origin_name, "value": entry})
            return normalized
        return []


class Stage(BaseModel):
    """Full Kargo Stage resource."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Stage"
    metadata: ObjectMeta
    spec: StageSpec = Field(default_factory=StageSpec)
    status: Optional[StageStatus] = None

    def get_current_freight_id(self) -> Optional[str]:
        """Resolve current freight ID from v1.12 freightHistory or legacy status."""
        if not self.status:
            return None
        if self.status.freight_history:
            first = self.status.freight_history[0]
            if isinstance(first, dict):
                items = first.get("items") or {}
                if isinstance(items, dict) and items:
                    first_origin_freight = next(iter(items.values()))
                    if isinstance(first_origin_freight, dict) and first_origin_freight.get("name"):
                        return str(first_origin_freight["name"])
                if first.get("id"):
                    return str(first["id"])
        if self.status.current_freight_id:
            return self.status.current_freight_id
        return None

    def get_previous_verified_freight_id(self) -> Optional[str]:
        """Resolve the most recent previous Freight in freightHistory that passed verification."""
        if not self.status or len(self.status.freight_history) < 2:
            return None
        for entry in self.status.freight_history[1:]:
            if not isinstance(entry, dict):
                continue
            verifications = entry.get("verificationHistory") or []
            # If verificationHistory exists, require at least one Successful run (or no failed run if unconfigured)
            if verifications:
                latest_v = verifications[0] if isinstance(verifications[0], dict) else {}
                if latest_v.get("phase") not in ("Successful", "Succeeded", None):
                    continue
            items = entry.get("items") or {}
            if isinstance(items, dict) and items:
                first_origin_freight = next(iter(items.values()))
                if isinstance(first_origin_freight, dict) and first_origin_freight.get("name"):
                    return str(first_origin_freight["name"])
            if entry.get("id"):
                return str(entry["id"])
        return None

    def get_latest_verification(self) -> Optional[Dict[str, Any]]:
        """Return the latest verificationHistory entry for current Freight, if any."""
        if not self.status or not self.status.freight_history:
            return None
        first = self.status.freight_history[0]
        if isinstance(first, dict):
            verifications = first.get("verificationHistory") or []
            if verifications and isinstance(verifications[0], dict):
                return verifications[0]
        return None

    def get_health_status(self) -> str:
        if not self.status:
            return "Unknown"
        if isinstance(self.status.health, dict) and self.status.health.get("status"):
            return str(self.status.health["status"])
        for cond in self.status.conditions:
            if cond.get("type") == "Healthy":
                return "Healthy" if cond.get("status") == "True" else (cond.get("reason") or "Unhealthy")
        return "Healthy"

    def get_phase(self) -> str:
        if not self.status:
            return "Ready"
        if self.status.current_promotion:
            return "Promoting"
        latest_v = self.get_latest_verification()
        if latest_v and latest_v.get("phase") in ("Pending", "Running"):
            return "Verifying"
        for cond in self.status.conditions:
            if cond.get("type") == "Ready" and cond.get("status") == "False":
                return str(cond.get("reason") or "NotReady")
        return "Ready"


class StageSummary(BaseModel):
    """Compact stage summary with DAG topology."""

    name: str
    namespace: str = ""
    phase: str = "Ready"
    health_status: str = "Healthy"
    warehouses: List[str] = Field(default_factory=list)
    upstream_stages: List[str] = Field(default_factory=list)
    downstream_stages: List[str] = Field(default_factory=list)
    current_freight_id: Optional[str] = None
    auto_promotion_enabled: bool = False
    has_auto_promotion_hold: bool = False
