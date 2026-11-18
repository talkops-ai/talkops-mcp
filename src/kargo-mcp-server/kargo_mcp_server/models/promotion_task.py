"""Kargo PromotionTask and ClusterPromotionTask models."""

from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field

from kargo_mcp_server.models.common import ObjectMeta


class PromotionTaskSpec(BaseModel):
    """Specification for PromotionTask and ClusterPromotionTask."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    vars: List[Dict[str, Any]] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class PromotionTask(BaseModel):
    """Kargo PromotionTask or ClusterPromotionTask resource."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "PromotionTask"
    metadata: ObjectMeta
    spec: PromotionTaskSpec = Field(default_factory=PromotionTaskSpec)
