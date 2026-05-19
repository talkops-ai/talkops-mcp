"""Kargo Project models."""


from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from kargo_mcp_server.models.common import ObjectMeta


class PromotionPolicy(BaseModel):
    """Project-level promotion policy configuration."""

    auto_promotion_enabled: bool = Field(default=True, alias="autoPromotionEnabled")
    selection_strategy: Optional[str] = Field(default=None, alias="selectionStrategy")

    model_config = {"populate_by_name": True}


class ProjectSpec(BaseModel):
    """Project specification."""

    promotion_policy: Optional[PromotionPolicy] = Field(
        default=None, alias="promotionPolicy"
    )

    model_config = {"populate_by_name": True}


class ProjectStatus(BaseModel):
    """Project status."""

    conditions: List[Dict[str, Any]] = Field(default_factory=list)


class Project(BaseModel):
    """Full Kargo Project resource."""

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Project"
    metadata: ObjectMeta
    spec: ProjectSpec = Field(default_factory=ProjectSpec)
    status: Optional[ProjectStatus] = None


class ProjectSummary(BaseModel):
    """Compact project summary for MCP tool/resource responses."""

    name: str
    namespace: str = ""
    stage_count: int = 0
    auto_promotion_enabled: bool = True
