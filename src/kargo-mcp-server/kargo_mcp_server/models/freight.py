"""Kargo Freight models (Kargo v1.10–v1.12)."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from kargo_mcp_server.models.common import ObjectMeta


class FreightOrigin(BaseModel):
    """Origin Warehouse of a Freight item."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kind: str = "Warehouse"
    name: str = ""


class GitCommitArtifact(BaseModel):
    """Git commit reference in a Freight item."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    repo_url: str = Field(default="", alias="repoURL")
    id: str = ""
    branch: Optional[str] = None
    tag: Optional[str] = None
    message: Optional[str] = None
    author: Optional[str] = None


class ImageArtifact(BaseModel):
    """Container image reference in a Freight item."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    repo_url: str = Field(default="", alias="repoURL")
    tag: Optional[str] = None
    digest: Optional[str] = None
    annotations: Dict[str, str] = Field(default_factory=dict)


class ChartArtifact(BaseModel):
    """Helm chart reference in a Freight item."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    repo_url: str = Field(default="", alias="repoURL")
    name: Optional[str] = None
    version: str = ""


class ArtifactReference(BaseModel):
    """Normalized summary reference to a versioned artifact inside Freight."""

    type: str   # "image", "git", "chart", or generic subscription type
    repo_url: str = ""
    version: str = ""
    detail: Optional[str] = None


class FreightStageState(BaseModel):
    """Normalized per-stage state of a Freight item."""

    stage: str
    currently_in: bool = False
    verified: bool = False
    approved: bool = False
    verified_at: Optional[str] = None
    approved_at: Optional[str] = None
    longest_soak: Optional[str] = None


class FreightStatus(BaseModel):
    """Kargo v1.12 Freight status."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    currently_in: Dict[str, Any] = Field(default_factory=dict, alias="currentlyIn")
    verified_in: Dict[str, Any] = Field(default_factory=dict, alias="verifiedIn")
    approved_for: Dict[str, Any] = Field(default_factory=dict, alias="approvedFor")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Freight(BaseModel):
    """Full Kargo Freight resource (Kargo v1.12 top-level fields)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    apiVersion: str = "kargo.akuity.io/v1alpha1"
    kind: str = "Freight"
    metadata: ObjectMeta
    alias: Optional[str] = None
    origin: Optional[FreightOrigin] = None
    commits: List[GitCommitArtifact] = Field(default_factory=list)
    images: List[ImageArtifact] = Field(default_factory=list)
    charts: List[ChartArtifact] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    discovered_at: Optional[datetime] = Field(default=None, alias="discoveredAt")
    status: Optional[FreightStatus] = None

    def get_alias(self) -> Optional[str]:
        if self.alias:
            return self.alias
        return self.metadata.labels.get("kargo.akuity.io/alias")

    def get_origin_name(self) -> str:
        if self.origin and self.origin.name:
            return self.origin.name
        return ""

    def normalized_artifacts(self) -> List[ArtifactReference]:
        items: List[ArtifactReference] = []
        for img in self.images:
            items.append(
                ArtifactReference(
                    type="image",
                    repo_url=img.repo_url,
                    version=img.tag or img.digest or "",
                    detail=img.digest,
                )
            )
        for commit in self.commits:
            items.append(
                ArtifactReference(
                    type="git",
                    repo_url=commit.repo_url,
                    version=commit.tag or commit.id[:12] if commit.id else "",
                    detail=commit.branch or commit.message,
                )
            )
        for chart in self.charts:
            items.append(
                ArtifactReference(
                    type="chart",
                    repo_url=chart.repo_url,
                    version=chart.version,
                    detail=chart.name,
                )
            )
        for art in self.artifacts:
            if isinstance(art, dict):
                items.append(
                    ArtifactReference(
                        type=str(art.get("type", "artifact")),
                        repo_url=str(art.get("repoURL", art.get("subscriptionName", ""))),
                        version=str(art.get("version", art.get("ref", ""))),
                    )
                )
        return items

    def normalized_stage_states(self) -> List[FreightStageState]:
        if not self.status:
            return []
        currently = self.status.currently_in or {}
        verified = self.status.verified_in or {}
        approved = self.status.approved_for or {}
        all_stages = sorted(set(currently.keys()) | set(verified.keys()) | set(approved.keys()))
        result: List[FreightStageState] = []
        for stg in all_stages:
            v_info = verified.get(stg) or {}
            a_info = approved.get(stg) or {}
            result.append(
                FreightStageState(
                    stage=stg,
                    currently_in=stg in currently,
                    verified=stg in verified,
                    approved=stg in approved,
                    verified_at=v_info.get("verifiedAt") if isinstance(v_info, dict) else None,
                    approved_at=a_info.get("approvedAt") if isinstance(a_info, dict) else None,
                    longest_soak=v_info.get("longestSoak") if isinstance(v_info, dict) else None,
                )
            )
        return result

    def to_summary(self) -> "FreightSummary":
        stage_states = self.normalized_stage_states()
        return FreightSummary(
            id=self.metadata.name,
            alias=self.get_alias(),
            origin=self.get_origin_name(),
            discovered_at=self.discovered_at.isoformat() if self.discovered_at else (
                self.metadata.creationTimestamp.isoformat() if self.metadata.creationTimestamp else None
            ),
            artifacts=self.normalized_artifacts(),
            currently_in=[s.stage for s in stage_states if s.currently_in],
            verified_in=[s.stage for s in stage_states if s.verified],
            approved_for=[s.stage for s in stage_states if s.approved],
            per_stage=stage_states,
        )


class FreightSummary(BaseModel):
    """Compact freight summary for MCP tool/resource responses."""

    id: str
    alias: Optional[str] = None
    origin: str = ""
    discovered_at: Optional[str] = None
    artifacts: List[ArtifactReference] = Field(default_factory=list)
    currently_in: List[str] = Field(default_factory=list)
    verified_in: List[str] = Field(default_factory=list)
    approved_for: List[str] = Field(default_factory=list)
    per_stage: List[FreightStageState] = Field(default_factory=list)
