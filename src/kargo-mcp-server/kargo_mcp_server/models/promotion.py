"""Kargo Promotion models."""


from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, Field

from kargo_mcp_server.models.common import ObjectMeta


class PromotionStepStatus(BaseModel):
    """Status of a single promotion step."""

    name: str
    type: str
    status: str
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    finished_at: Optional[datetime] = Field(default=None, alias="finishedAt")
    log_url: Optional[str] = Field(default=None, alias="logUrl")

    model_config = {"populate_by_name": True}


class PromotionSpec(BaseModel):
    """Promotion specification.

    Matches the Kargo Swagger PromotionSpec definition.
    The primary field is ``freight`` (a single Freight resource name).
    ``project`` is not part of the Kargo spec but may appear in some
    API responses so it is kept as optional for resilience.
    """

    stage: str
    # Accept both "freight" (Swagger-canonical) and legacy "freightId"
    freight: str = Field(
        validation_alias=AliasChoices("freight", "freightId"),
    )
    project: Optional[str] = None

    model_config = {"populate_by_name": True}


class PromotionStatus(BaseModel):
    """Promotion status."""

    state: str = "Unknown"
    message: Optional[str] = None
    steps: List[PromotionStepStatus] = Field(default_factory=list)
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    finished_at: Optional[datetime] = Field(default=None, alias="finishedAt")

    model_config = {"populate_by_name": True}


class Promotion(BaseModel):
    """Full Kargo Promotion resource."""

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Promotion"
    metadata: ObjectMeta
    spec: PromotionSpec
    status: Optional[PromotionStatus] = None


class PromotionSummary(BaseModel):
    """Compact promotion summary."""

    name: str
    stage: str
    freight: str
    state: str = "Unknown"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
