"""Kargo Freight models."""


from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from kargo_mcp_server.models.common import ObjectMeta


class ArtifactReference(BaseModel):
    """Reference to a versioned artifact within a Freight."""

    type: str   # "image", "git", "helm"
    ref: str    # repo/tag, commit SHA, chart version


class FreightSpec(BaseModel):
    """Freight specification."""

    artifacts: List[ArtifactReference] = Field(default_factory=list)


class FreightStageState(BaseModel):
    """Per-stage state of a freight item."""

    stage: str
    available: bool = False
    promoted: bool = False
    verified: bool = False


class FreightStatus(BaseModel):
    """Freight status."""

    discovered_time: Optional[datetime] = Field(default=None, alias="discoveredTime")
    stage_states: List[FreightStageState] = Field(default_factory=list, alias="stageStates")
    message: Optional[str] = None
    state: Optional[str] = None

    model_config = {"populate_by_name": True}


class Freight(BaseModel):
    """Full Kargo Freight resource."""

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Freight"
    metadata: ObjectMeta
    spec: FreightSpec = Field(default_factory=FreightSpec)
    status: Optional[FreightStatus] = None


class FreightSummary(BaseModel):
    """Compact freight summary."""

    id: str
    artifacts: List[ArtifactReference] = Field(default_factory=list)
    per_stage: List[FreightStageState] = Field(default_factory=list)
