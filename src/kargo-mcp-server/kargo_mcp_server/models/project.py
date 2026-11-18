"""Kargo Project and ProjectConfig models (Kargo v1.10–v1.12)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from kargo_mcp_server.models.common import ObjectMeta


class StageSelector(BaseModel):
    """Selector matching stages in a ProjectConfig promotionPolicy."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: Optional[str] = None
    match_labels: Optional[Dict[str, str]] = Field(default=None, alias="matchLabels")
    match_expressions: Optional[List[Dict[str, Any]]] = Field(
        default=None, alias="matchExpressions"
    )


class PromotionPolicy(BaseModel):
    """Promotion policy entry in ProjectConfig.spec.promotionPolicies."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    stage: Optional[str] = None
    stage_selector: Optional[StageSelector] = Field(default=None, alias="stageSelector")
    auto_promotion_enabled: bool = Field(default=False, alias="autoPromotionEnabled")


class ProjectConfigSpec(BaseModel):
    """ProjectConfig specification (replaces removed Project.spec since Kargo v1.7)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    promotion_policies: List[PromotionPolicy] = Field(
        default_factory=list, alias="promotionPolicies"
    )
    webhook_receivers: List[Dict[str, Any]] = Field(
        default_factory=list, alias="webhookReceivers"
    )
    freight_links: List[Dict[str, Any]] = Field(
        default_factory=list, alias="freightLinks"
    )
    stage_links: List[Dict[str, Any]] = Field(
        default_factory=list, alias="stageLinks"
    )


class ProjectConfigStatus(BaseModel):
    """ProjectConfig status including generated webhook receiver URLs."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    webhook_receivers: List[Dict[str, Any]] = Field(
        default_factory=list, alias="webhookReceivers"
    )
    last_handled_refresh: Optional[str] = Field(
        default=None, alias="lastHandledRefresh"
    )


class ProjectConfig(BaseModel):
    """Kargo ProjectConfig CRD (namespaced, name == project name)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "ProjectConfig"
    metadata: ObjectMeta
    spec: ProjectConfigSpec = Field(default_factory=ProjectConfigSpec)
    status: Optional[ProjectConfigStatus] = None


class ProjectStatus(BaseModel):
    """Project status."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    phase: Optional[str] = None


class Project(BaseModel):
    """Full Kargo Project resource (cluster-scoped; spec removed in v1.7)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Project"
    metadata: ObjectMeta
    status: Optional[ProjectStatus] = None

    def is_ready(self) -> bool:
        if not self.status:
            return True
        for cond in self.status.conditions:
            if cond.get("type") == "Ready":
                return cond.get("status") == "True"
        return True


class ProjectSummary(BaseModel):
    """Compact project summary for MCP responses."""

    name: str
    ready: bool = True
    phase: str = "Ready"
    creation_timestamp: Optional[str] = None
    auto_promotion_policies_count: int = 0
    webhook_receivers_count: int = 0
