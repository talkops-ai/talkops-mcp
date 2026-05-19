"""Kargo PromotionTask models."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from kargo_mcp_server.models.common import ObjectMeta


class PromotionTask(BaseModel):
    """Full Kargo PromotionTask resource."""

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "PromotionTask"
    metadata: ObjectMeta
    spec: Dict[str, Any] = Field(default_factory=dict)
