"""Pydantic input and output models for Kargo MCP Server tools."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class StagePromotionTemplateConfig(BaseModel):
    """Promotion template options for a Kargo Stage (inline steps or PromotionTask reference)."""

    model_config = ConfigDict(extra="allow")

    task_name: Optional[str] = Field(
        default=None,
        description="Name of a PromotionTask or ClusterPromotionTask to invoke.",
    )
    task_kind: Literal["PromotionTask", "ClusterPromotionTask"] = Field(
        default="PromotionTask",
        description="Kind of task reference when task_name is set.",
    )
    steps: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Inline promotion steps (e.g. [{'uses': 'git-clone', 'config': {...}}, ...]).",
    )
    vars: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Template-scoped variables as [{'name': '...', 'value': '...'}].",
    )


class StageVerificationConfig(BaseModel):
    """Verification options for a Kargo Stage using Argo Rollouts AnalysisTemplates."""

    model_config = ConfigDict(extra="allow")

    analysis_templates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "List of AnalysisTemplate references, e.g. "
            "[{'name': 'smoke-test', 'kind': 'AnalysisTemplate'}]."
        ),
    )
    args: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Arguments passed to AnalysisRuns as [{'name': '...', 'value': '...'}].",
    )
    analysis_run_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional labels/annotations applied to spawned AnalysisRuns.",
    )


class CredentialOptions(BaseModel):
    """Configuration for server-managed Kargo repository, generic credentials, or ConfigMaps.

    Security invariant (0->1 omission): This model never accepts raw passwords,
    tokens, or private keys. The server resolves secret material exclusively from
    server-side environment variables or mounted credential files referenced by
    ``secret_ref``.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["repo", "generic", "configmap"] = Field(
        default="repo",
        description="Resource kind: 'repo' (git/helm/image Secret), 'generic' (Secret), or 'configmap'.",
    )
    cred_type: Optional[Literal["git", "helm", "image"]] = Field(
        default=None,
        description="Repository credential type when kind='repo' ('git', 'helm', or 'image').",
    )
    repo_url: Optional[str] = Field(
        default=None,
        description="Repository URL or regex pattern when kind='repo'.",
    )
    repo_url_is_regex: bool = Field(
        default=False,
        description="Whether repo_url is a regular expression matching multiple repositories.",
    )
    secret_ref: Optional[str] = Field(
        default=None,
        description=(
            "Symbolic reference name used by the server to look up credentials from "
            "environment variables (KARGO_CRED_<REF>_USERNAME / KARGO_CRED_<REF>_PASSWORD "
            "or default KARGO_REPO_USERNAME / KARGO_REPO_PASSWORD) or mounted KARGO_CREDENTIALS_FILE."
        ),
    )
    data_keys: Optional[List[str]] = Field(
        default=None,
        description=(
            "For generic credentials or configmaps, list of key names to populate from "
            "the referenced server-side secret_ref entry or non-sensitive config_data."
        ),
    )
    config_data: Optional[Dict[str, str]] = Field(
        default=None,
        description="Non-secret key/value pairs for kind='configmap' only.",
    )
    replicate_to_all_projects: bool = Field(
        default=False,
        description="When scope='shared', set annotation kargo.akuity.io/replicate-to='*'.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description annotation (`kargo.akuity.io/description`).",
    )


class ExecutionResult(BaseModel):
    """Standard concise response returned by mutating and destructive MCP tools."""

    status: Literal[
        "success",
        "preview",
        "confirmation_required",
        "cancelled",
        "aborted",
    ] = Field(description="Execution outcome status.")
    summary: str = Field(
        description="Concise human- and model-readable outcome summary."
    )
    dry_run: bool = Field(
        default=False,
        description="True when returned as a dry-run preview without cluster mutation.",
    )
    manifest: Optional[str] = Field(
        default=None,
        description="Rendered YAML manifest or promotion plan preview.",
    )
    resource_uri: Optional[str] = Field(
        default=None,
        description="MCP Resource URI to inspect the target resource without spending a tool turn.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Operational or safety warnings detected during execution.",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Compact operation-specific fields (~5 essential fields).",
    )


class FreightQueryReport(BaseModel):
    """Concise freight query result returned by kargo_query_freight."""

    project: str = Field(description="Kargo project name.")
    total: int = Field(description="Total matching freight items.")
    summary: str = Field(description="Concise summary of discovered freight.")
    stage_filter: Optional[str] = Field(
        default=None, description="Stage availability filter if applied."
    )
    warehouse_filter: Optional[str] = Field(
        default=None, description="Origin Warehouse filter if applied."
    )
    items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Concise freight summaries (id, alias, origin, artifacts, stages).",
    )
    resource_uri: str = Field(
        description="Pipeline resource URI for full context."
    )


class FreightTraceReport(BaseModel):
    """End-to-end delivery trace for a Freight or artifact across the Stage DAG (N-to-1 tool)."""

    project: str = Field(description="Kargo project name.")
    freight_id: str = Field(description="Resolved Freight SHA-1 name.")
    alias: Optional[str] = Field(default=None, description="Human-friendly Freight alias.")
    origin: str = Field(default="", description="Origin Warehouse name.")
    summary: str = Field(description="End-to-end progression summary across all Stages.")
    artifacts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Versioned git commits, container images, and Helm charts in this Freight.",
    )
    stages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Per-stage progression status (stage, currently_in, verified, approved, "
            "eligible_for_promotion, blocker_reason)."
        ),
    )
    blockers: List[str] = Field(
        default_factory=list,
        description="Actionable reasons blocking progression to downstream stages.",
    )
    resource_uri: str = Field(description="MCP Resource URI for full Freight details.")


class StageDiagnosisReport(BaseModel):
    """Correlated diagnostic report returned by kargo_diagnose_stage (N-to-1 tool)."""

    project: str = Field(description="Kargo project name.")
    stage: str = Field(description="Stage name.")
    phase: str = Field(description="Current Stage phase (Ready, Promoting, Verifying, NotReady).")
    health_status: str = Field(
        default="Healthy",
        description="Stage health status (Healthy, Unhealthy, Progressing, Unknown).",
    )
    current_freight: Optional[str] = Field(
        default=None, description="Currently deployed Freight ID."
    )
    auto_promotion_enabled: bool = Field(
        default=False, description="Whether auto-promotion is enabled for this Stage in ProjectConfig."
    )
    auto_promotion_holds: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Active auto-promotion holds (e.g. established after a rollback in Kargo v1.11+).",
    )
    summary: str = Field(description="Concise root-cause and remediation summary.")
    diagnosis_codes: List[str] = Field(
        default_factory=list,
        description="Standardized diagnosis codes mapping to troubleshooting-kargo-pipelines catalog.",
    )
    conditions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Stage status conditions."
    )
    failed_promotion: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Details of the failed/errored/running Promotion and failing step.",
    )
    verification: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Latest verification status and AnalysisRun summary.",
    )
    warning_events: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Recent project Warning events correlated to this Stage.",
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Actionable MCP tool remediation calls.",
    )


class WarehouseDiagnosisReport(BaseModel):
    """Correlated diagnostic report returned by kargo_diagnose_warehouse (N-to-1 tool)."""

    project: str = Field(description="Kargo project name.")
    warehouse: str = Field(description="Warehouse name.")
    ready: bool = Field(default=True, description="True when Warehouse discovery is healthy.")
    last_freight_id: Optional[str] = Field(
        default=None, description="Most recently produced Freight ID."
    )
    summary: str = Field(description="Concise discovery and configuration diagnosis summary.")
    diagnosis_codes: List[str] = Field(
        default_factory=list,
        description="Standardized diagnosis codes mapping to troubleshooting-kargo-pipelines catalog.",
    )
    subscriptions_count: int = Field(
        default=0, description="Number of configured artifact subscriptions."
    )
    discovered_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of discovered artifacts per subscription type (git, images, charts).",
    )
    deprecated_fields: List[str] = Field(
        default_factory=list,
        description="Removed or breaking Kargo v1.9-v1.12 fields detected in subscriptions.",
    )
    conditions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Warehouse status conditions."
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Actionable MCP tool remediation calls.",
    )
