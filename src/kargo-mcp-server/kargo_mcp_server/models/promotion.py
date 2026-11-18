"""Kargo Promotion models (Kargo v1.10–v1.12)."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from kargo_mcp_server.models.common import ObjectMeta


class PromotionStepExecutionMetadata(BaseModel):
    """Execution metadata for a single step in Promotion.status.stepExecutionMetadata."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    alias: str = Field(default="", validation_alias=AliasChoices("alias", "name"))
    status: str = "Unknown"
    message: Optional[str] = None
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    finished_at: Optional[datetime] = Field(default=None, alias="finishedAt")
    error_count: int = Field(default=0, alias="errorCount")


class PromotionSpec(BaseModel):
    """Promotion specification (Kargo v1.12)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    stage: str
    freight: str = Field(
        default="",
        validation_alias=AliasChoices("freight", "freightId"),
    )
    origin: Optional[Dict[str, Any]] = None
    vars: List[Dict[str, Any]] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class PromotionStatus(BaseModel):
    """Promotion status (Kargo v1.12 uses phase; legacy used state)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    phase: str = Field(
        default="Pending",
        validation_alias=AliasChoices("phase", "state"),
    )
    message: Optional[str] = None
    current_step: Optional[int] = Field(default=None, alias="currentStep")
    step_execution_metadata: List[PromotionStepExecutionMetadata] = Field(
        default_factory=list,
        validation_alias=AliasChoices("stepExecutionMetadata", "steps"),
    )
    state: Optional[Dict[str, Any]] = None  # v1.12 step output state map if dict
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    finished_at: Optional[datetime] = Field(default=None, alias="finishedAt")
    freight: Optional[Dict[str, Any]] = None
    freight_collection: Optional[Dict[str, Any]] = Field(
        default=None, alias="freightCollection"
    )
    health_checks: List[Dict[str, Any]] = Field(
        default_factory=list, alias="healthChecks"
    )


class Promotion(BaseModel):
    """Full Kargo Promotion resource."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Promotion"
    metadata: ObjectMeta
    spec: PromotionSpec
    status: Optional[PromotionStatus] = None

    def get_phase(self) -> str:
        if not self.status:
            return "Pending"
        return self.status.phase or "Unknown"


class PromotionSummary(BaseModel):
    """Compact promotion summary."""

    name: str
    stage: str
    freight: str
    phase: str = "Pending"
    message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
