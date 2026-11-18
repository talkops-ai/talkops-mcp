"""Kargo pipeline configuration tools (Toolset: pipeline).

Covers Project lifecycle, ProjectConfig (promotionPolicies, webhookReceivers, deep links),
Warehouse subscriptions, Stage DAG & templates, PromotionTask/ClusterPromotionTask definitions,
and declarative resource deletion.
"""

from typing import Any, Dict, List, Literal, Optional
import yaml
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from kargo_mcp_server.exceptions.custom import KargoValidationError
from kargo_mcp_server.models.schemas import (
    ExecutionResult,
    StagePromotionTemplateConfig,
    StageVerificationConfig,
)
from kargo_mcp_server.tools.base import BaseTool, confirm_destructive_action
from kargo_mcp_server.utils.kargo_helpers import (
    build_requested_freight,
    validate_promotion_steps,
)
from kargo_mcp_server.utils.warehouse_spec_builder import build_warehouse_spec


class PipelineTools(BaseTool):
    """Tools for configuring Kargo Projects, ProjectConfigs, Warehouses, Stages, and PromotionTasks."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register pipeline configuration tools with FastMCP."""
        if not self.should_register("pipeline", is_write=True):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Kargo Project",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_manage_project(
            action: Literal["create", "delete"] = Field(
                ..., description="Operation to perform: 'create' or 'delete'."
            ),
            name: str = Field(..., min_length=1, description="Kargo Project name."),
            keep_namespace: bool = Field(
                default=False,
                description="Set annotation kargo.akuity.io/keep-namespace='true' so Kubernetes namespace is retained on delete.",
            ),
            description: Optional[str] = Field(
                default=None,
                description="Optional human-readable project description annotation.",
            ),
            dry_run: bool = Field(
                default=True,
                description="Preview the Project manifest without creating it on the cluster (applies to action='create').",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm permanent project deletion when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Create or delete a Kargo Project (cluster-scoped organizational boundary).

            Note: In Kargo v1.7+, Project.spec was removed; configure auto-promotion policies
            and webhook receivers via kargo_apply_project_config.
            """
            self.check_write_access("kargo_manage_project")
            resource_uri = f"kargo://projects/{name}"

            try:
                if action == "create":
                    annotations: Dict[str, str] = {}
                    if keep_namespace:
                        annotations["kargo.akuity.io/keep-namespace"] = "true"
                    if description:
                        annotations["kargo.akuity.io/description"] = description
                    metadata: Dict[str, Any] = {"name": name}
                    if annotations:
                        metadata["annotations"] = annotations
                    manifest_dict: Dict[str, Any] = {
                        "apiVersion": "kargo.akuity.io/v1alpha1",
                        "kind": "Project",
                        "metadata": metadata,
                    }
                    manifest_yaml = yaml.dump(manifest_dict, default_flow_style=False)

                    if dry_run:
                        return ExecutionResult(
                            status="preview",
                            summary=f"Previewed Project '{name}' manifest (dry_run=True). Re-run with dry_run=False to create.",
                            dry_run=True,
                            manifest=manifest_yaml,
                            resource_uri=resource_uri,
                            details={"name": name, "keep_namespace": keep_namespace},
                        )

                    created = await self.kargo_service.create_project(
                        name=name,
                        keep_namespace=keep_namespace,
                        description=description,
                    )
                    return ExecutionResult(
                        status="success",
                        summary=f"Created Kargo Project '{created.metadata.name}'.",
                        dry_run=False,
                        manifest=manifest_yaml,
                        resource_uri=resource_uri,
                        details={"name": created.metadata.name, "keep_namespace": keep_namespace},
                    )

                # action == "delete"
                if not await confirm_destructive_action(
                    ctx,
                    action_summary=f"Delete Kargo Project '{name}' and its pipeline resources",
                    confirm=confirm,
                    resource_uri=resource_uri,
                    details={"name": name},
                ):
                    return ExecutionResult(
                        status="cancelled",
                        summary=(
                            f"Confirmation required to delete Project '{name}'. "
                            "Re-run with confirm=True after user approval."
                        ),
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={"name": name, "requires_confirmation": True},
                    )

                await self.kargo_service.delete_project(name)
                return ExecutionResult(
                    status="success",
                    summary=f"Deleted Kargo Project '{name}'.",
                    dry_run=False,
                    resource_uri="kargo://projects",
                    details={"name": name},
                )
            except Exception as exc:
                self.handle_error(exc, "kargo_manage_project", project=name, resource_name=name)
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply Kargo ProjectConfig",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_apply_project_config(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            promotion_policies: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "List of promotion policies, e.g. [{'stageSelector': {'name': 'dev'}, "
                    "'autoPromotionEnabled': True}]."
                ),
            ),
            webhook_receivers: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "List of webhook receivers (github, gitlab, bitbucket, dockerhub, quay, "
                    "azure, gitea, harbor, artifactory, generic), e.g. "
                    "[{'name': 'gh-wh', 'github': {'secretRef': {'name': 'gh-webhook-secret'}}}]"
                ),
            ),
            freight_links: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Optional UI deep links for Freight items ([{'title': '...', 'url': '...'}]).",
            ),
            stage_links: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Optional UI deep links for Stages ([{'title': '...', 'url': '...'}]).",
            ),
            dry_run: bool = Field(
                default=True,
                description="Preview the merged ProjectConfig YAML without applying (default: True).",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Configure a Kargo ProjectConfig CRD (auto-promotion policies, webhook receivers, and UI links).

            In Kargo v1.5+, ProjectConfig (named identically to the project) replaces the removed Project.spec.
            Merges provided sections with any existing ProjectConfig on the cluster.
            """
            self.check_write_access("kargo_apply_project_config")
            resource_uri = f"kargo://projects/{project}"

            try:
                existing_cfg = await self.kargo_service.get_project_config(project)
                spec: Dict[str, Any] = dict((existing_cfg.get("spec") or {}) if isinstance(existing_cfg, dict) else {})

                if promotion_policies is not None:
                    normalized_policies: List[Dict[str, Any]] = []
                    for pol in promotion_policies:
                        if not isinstance(pol, dict):
                            raise KargoValidationError("Each promotion_policies entry must be a dict.")
                        entry: Dict[str, Any] = {
                            "autoPromotionEnabled": bool(
                                pol.get("autoPromotionEnabled", pol.get("auto_promotion_enabled", True))
                            )
                        }
                        if "stageSelector" in pol or "stage_selector" in pol:
                            entry["stageSelector"] = pol.get("stageSelector") or pol.get("stage_selector")
                        elif "stage" in pol:
                            entry["stageSelector"] = {"name": pol["stage"]}
                        else:
                            raise KargoValidationError(
                                "Each promotion policy must include 'stage' or 'stageSelector' (e.g. {'stageSelector': {'name': 'dev'}, 'autoPromotionEnabled': True})."
                            )
                        normalized_policies.append(entry)
                    spec["promotionPolicies"] = normalized_policies

                if webhook_receivers is not None:
                    spec["webhookReceivers"] = webhook_receivers
                if freight_links is not None:
                    spec["freightLinks"] = freight_links
                if stage_links is not None:
                    spec["stageLinks"] = stage_links

                if not spec:
                    raise KargoValidationError(
                        "Provide at least one of promotion_policies, webhook_receivers, freight_links, or stage_links."
                    )

                manifest_dict = {
                    "apiVersion": "kargo.akuity.io/v1alpha1",
                    "kind": "ProjectConfig",
                    "metadata": {"name": project, "namespace": project},
                    "spec": spec,
                }
                manifest_yaml = yaml.dump(manifest_dict, default_flow_style=False)

                details = {
                    "project": project,
                    "promotion_policies_count": len(spec.get("promotionPolicies") or []),
                    "webhook_receivers_count": len(spec.get("webhookReceivers") or []),
                }

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=f"Previewed ProjectConfig for '{project}' (dry_run=True). Re-run with dry_run=False to apply.",
                        dry_run=True,
                        manifest=manifest_yaml,
                        resource_uri=resource_uri,
                        details=details,
                    )

                await self.kargo_service.upsert_project_config(project, spec)
                return ExecutionResult(
                    status="success",
                    summary=f"Applied ProjectConfig for project '{project}'.",
                    dry_run=False,
                    manifest=manifest_yaml,
                    resource_uri=resource_uri,
                    details=details,
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_apply_project_config", project=project, resource_name=project
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply Kargo Warehouse",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_apply_warehouse(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            name: str = Field(..., min_length=1, description="Warehouse name."),
            subscriptions: List[Dict[str, Any]] = Field(
                ...,
                description=(
                    "Artifact subscriptions list. Each item has 'type' ('image', 'git', 'chart') and 'repo_url' "
                    "(or nested Kargo subscription dict). Image options: constraint, image_selection_strategy, "
                    "allow_tags_regexes, ignore_tags_regexes, platform, cache_by_tag. Git options: branch, "
                    "commit_selection_strategy, semver_constraint, include_paths, exclude_paths, expression_filter, "
                    "since, blobless. Chart options: chart_name, semver_constraint."
                ),
            ),
            interval: Optional[str] = Field(
                default="5m0s",
                description="Polling interval in Go duration format (e.g. '5m0s', '1m').",
            ),
            freight_creation_policy: Literal["Automatic", "Manual"] = Field(
                default="Automatic",
                description="Freight creation mode ('Automatic' or 'Manual').",
            ),
            freight_creation_criteria: Optional[str] = Field(
                default=None,
                description="Optional Kargo v1.8+ expr-lang criteria evaluated before creating Freight.",
            ),
            dry_run: bool = Field(
                default=True,
                description="Preview the Warehouse YAML manifest without applying (default: True).",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Create or update a Kargo Warehouse with Git, Image, or Helm Chart subscriptions.

            Automatically emits Kargo v1.12 compliant subscription fields ('constraint' for images
            and 'allowTagsRegexes'/'ignoreTagsRegexes' instead of removed fields).
            """
            self.check_write_access("kargo_apply_warehouse")
            resource_uri = f"kargo://projects/{project}/warehouses/{name}"

            try:
                spec = build_warehouse_spec(
                    subscriptions=subscriptions,
                    freight_creation_policy=freight_creation_policy,
                    interval=interval,
                    freight_creation_criteria=freight_creation_criteria,
                )
                manifest_dict = {
                    "apiVersion": "kargo.akuity.io/v1alpha1",
                    "kind": "Warehouse",
                    "metadata": {"name": name, "namespace": project},
                    "spec": spec,
                }
                manifest_yaml = yaml.dump(manifest_dict, default_flow_style=False)
                details = {
                    "project": project,
                    "name": name,
                    "subscriptions_count": len(spec.get("subscriptions") or []),
                    "freight_creation_policy": freight_creation_policy,
                }

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=f"Previewed Warehouse '{name}' in project '{project}' (dry_run=True). Re-run with dry_run=False to apply.",
                        dry_run=True,
                        manifest=manifest_yaml,
                        resource_uri=resource_uri,
                        details=details,
                    )

                await self.kargo_service.upsert_warehouse(project, name, spec)
                return ExecutionResult(
                    status="success",
                    summary=f"Applied Warehouse '{name}' in project '{project}'.",
                    dry_run=False,
                    manifest=manifest_yaml,
                    resource_uri=resource_uri,
                    details=details,
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_apply_warehouse", project=project, resource_name=name
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply Kargo Stage",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_apply_stage(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            name: str = Field(..., min_length=1, description="Stage name (e.g. 'dev', 'staging', 'prod')."),
            requested_freight: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "Requested freight origins and upstream stages. Example root stage: "
                    "[{'kind': 'Warehouse', 'name': 'main-wh'}]. Example downstream stage: "
                    "[{'kind': 'Warehouse', 'name': 'main-wh', 'stages': ['dev'], "
                    "'availability_strategy': 'All', 'required_soak_time': '30m', 'selection_policy': 'MatchUpstream'}]."
                ),
            ),
            promotion_template: Optional[StagePromotionTemplateConfig] = Field(
                default=None,
                description="Promotion template referencing a PromotionTask/ClusterPromotionTask or inline steps.",
            ),
            verification: Optional[StageVerificationConfig] = Field(
                default=None,
                description="Post-promotion verification AnalysisTemplates and arguments.",
            ),
            vars: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Stage-level variables as [{'name': '...', 'value': '...'}] (Kargo v1.5+).",
            ),
            dry_run: bool = Field(
                default=True,
                description="Preview the merged Stage YAML manifest without applying (default: True).",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Create or update a Kargo Stage, merging updates with existing Stage spec and validating DAG cycles.

            Preserves existing Stage fields (verification, promotionTemplate, vars, requestedFreight)
            when performing partial updates, and validates inline promotion steps against Kargo v1.12.
            """
            self.check_write_access("kargo_apply_stage")
            resource_uri = f"kargo://projects/{project}/stages/{name}"

            try:
                spec_updates: Dict[str, Any] = {}
                warnings: List[str] = []

                if requested_freight is not None:
                    rf_models = build_requested_freight(requested_freight)
                    spec_updates["requestedFreight"] = [
                        rf.model_dump(by_alias=True, exclude_none=True) for rf in rf_models
                    ]

                if vars is not None:
                    spec_updates["vars"] = vars

                if promotion_template is not None:
                    pt_cfg = (
                        promotion_template
                        if isinstance(promotion_template, StagePromotionTemplateConfig)
                        else StagePromotionTemplateConfig.model_validate(promotion_template)
                    )
                    pt_spec: Dict[str, Any] = {}
                    if pt_cfg.vars:
                        pt_spec["vars"] = pt_cfg.vars
                    if pt_cfg.steps:
                        errs, step_warns = validate_promotion_steps(pt_cfg.steps)
                        if errs:
                            raise KargoValidationError("; ".join(errs))
                        warnings.extend(step_warns)
                        pt_spec["steps"] = pt_cfg.steps
                    elif pt_cfg.task_name:
                        task_ref: Dict[str, Any] = {"name": pt_cfg.task_name}
                        if pt_cfg.task_kind == "ClusterPromotionTask":
                            task_ref["kind"] = "ClusterPromotionTask"
                        pt_spec["steps"] = [{"task": task_ref}]
                    if pt_spec:
                        spec_updates["promotionTemplate"] = {"spec": pt_spec}

                if verification is not None:
                    v_cfg = (
                        verification
                        if isinstance(verification, StageVerificationConfig)
                        else StageVerificationConfig.model_validate(verification)
                    )
                    v_dict: Dict[str, Any] = {
                        "analysisTemplates": v_cfg.analysis_templates,
                    }
                    if v_cfg.args:
                        v_dict["args"] = v_cfg.args
                    if v_cfg.analysis_run_metadata:
                        v_dict["analysisRunMetadata"] = v_cfg.analysis_run_metadata
                    spec_updates["verification"] = v_dict

                manifest_dict = await self.kargo_service.build_merged_stage_manifest(
                    project=project,
                    stage=name,
                    spec_updates=spec_updates,
                    merge_existing=True,
                )
                if not manifest_dict.get("spec", {}).get("requestedFreight"):
                    raise KargoValidationError(
                        f"Stage '{name}' requires 'requested_freight' when creating a new Stage."
                    )

                manifest_yaml = yaml.dump(manifest_dict, default_flow_style=False)
                details = {
                    "project": project,
                    "name": name,
                    "requested_freight_count": len(
                        manifest_dict.get("spec", {}).get("requestedFreight") or []
                    ),
                    "has_verification": bool(manifest_dict.get("spec", {}).get("verification")),
                }

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=f"Previewed Stage '{name}' in project '{project}' (dry_run=True). Re-run with dry_run=False to apply.",
                        dry_run=True,
                        manifest=manifest_yaml,
                        resource_uri=resource_uri,
                        warnings=warnings,
                        details=details,
                    )

                await self.kargo_service.upsert_stage(
                    project=project,
                    stage=name,
                    spec=manifest_dict["spec"],
                    merge_existing=False,
                )
                return ExecutionResult(
                    status="success",
                    summary=f"Applied Stage '{name}' in project '{project}'.",
                    dry_run=False,
                    manifest=manifest_yaml,
                    resource_uri=resource_uri,
                    warnings=warnings,
                    details=details,
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_apply_stage", project=project, resource_name=name
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply Kargo PromotionTask",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_apply_promotion_task(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            name: str = Field(..., min_length=1, description="PromotionTask or ClusterPromotionTask name."),
            steps: List[Dict[str, Any]] = Field(
                ...,
                description=(
                    "Promotion step definitions, e.g. [{'uses': 'git-clone', 'config': {...}}, "
                    "{'uses': 'yaml-update', 'as': 'update-img', 'config': {...}}]."
                ),
            ),
            vars: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description="Task variables as [{'name': 'repoURL', 'value': 'https://...'}].",
            ),
            scope: Literal["project", "cluster"] = Field(
                default="project",
                description="Scope: 'project' (PromotionTask) or 'cluster' (ClusterPromotionTask).",
            ),
            dry_run: bool = Field(
                default=True,
                description="Preview the PromotionTask YAML manifest without applying (default: True).",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Create or update a reusable Kargo PromotionTask or ClusterPromotionTask.

            Validates all step runner names and config keys against Kargo v1.12 (rejecting removed
            runners such as 'helm-update-image' and removed fields such as 'fromOrigin'/'git-commit.author').
            """
            self.check_write_access("kargo_apply_promotion_task")
            kind = "ClusterPromotionTask" if scope == "cluster" else "PromotionTask"
            resource_uri = (
                f"kargo://cluster-promotion-tasks/{name}"
                if scope == "cluster"
                else f"kargo://projects/{project}/promotion-tasks/{name}"
            )

            try:
                errors, warnings = validate_promotion_steps(steps)
                if errors:
                    raise KargoValidationError("; ".join(errors))

                spec: Dict[str, Any] = {"steps": steps}
                if vars:
                    spec["vars"] = vars

                metadata: Dict[str, Any] = {"name": name}
                if scope != "cluster":
                    metadata["namespace"] = project

                manifest_dict = {
                    "apiVersion": "kargo.akuity.io/v1alpha1",
                    "kind": kind,
                    "metadata": metadata,
                    "spec": spec,
                }
                manifest_yaml = yaml.dump(manifest_dict, default_flow_style=False)
                details = {
                    "project": project,
                    "name": name,
                    "kind": kind,
                    "steps_count": len(steps),
                }

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=f"Previewed {kind} '{name}' (dry_run=True). Re-run with dry_run=False to apply.",
                        dry_run=True,
                        manifest=manifest_yaml,
                        resource_uri=resource_uri,
                        warnings=warnings,
                        details=details,
                    )

                await self.kargo_service.upsert_promotion_task(
                    project=project,
                    name=name,
                    spec=spec,
                    scope=scope,
                )
                return ExecutionResult(
                    status="success",
                    summary=f"Applied {kind} '{name}'.",
                    dry_run=False,
                    manifest=manifest_yaml,
                    resource_uri=resource_uri,
                    warnings=warnings,
                    details=details,
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_apply_promotion_task", project=project, resource_name=name
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Kargo Pipeline Resource",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_delete_resource(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            kind: Literal[
                "Stage",
                "Warehouse",
                "PromotionTask",
                "ClusterPromotionTask",
                "ProjectConfig",
            ] = Field(..., description="Kargo resource kind to delete."),
            name: str = Field(..., min_length=1, description="Resource name to delete."),
            confirm: bool = Field(
                default=False,
                description="Confirm permanent deletion when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Delete a Kargo Stage, Warehouse, PromotionTask, ClusterPromotionTask, or ProjectConfig after confirmation."""
            self.check_write_access("kargo_delete_resource")
            resource_uri = f"kargo://projects/{project}/pipeline"

            try:
                if not await confirm_destructive_action(
                    ctx,
                    action_summary=f"Delete {kind} '{name}' in project '{project}'",
                    confirm=confirm,
                    resource_uri=resource_uri,
                    details={"project": project, "kind": kind, "name": name},
                ):
                    return ExecutionResult(
                        status="cancelled",
                        summary=(
                            f"Confirmation required to delete {kind} '{name}' in project '{project}'. "
                            "Re-run with confirm=True after user approval."
                        ),
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={
                            "project": project,
                            "kind": kind,
                            "name": name,
                            "requires_confirmation": True,
                        },
                    )

                if kind == "Stage":
                    await self.kargo_service.delete_stage(project, name)
                elif kind == "Warehouse":
                    await self.kargo_service.delete_warehouse(project, name)
                elif kind == "PromotionTask":
                    await self.kargo_service.delete_promotion_task(
                        project, name, scope="project"
                    )
                elif kind == "ClusterPromotionTask":
                    await self.kargo_service.delete_promotion_task(
                        project, name, scope="cluster"
                    )
                elif kind == "ProjectConfig":
                    await self.kargo_service.delete_project_config(project)

                return ExecutionResult(
                    status="success",
                    summary=f"Deleted {kind} '{name}' in project '{project}'.",
                    dry_run=False,
                    resource_uri=resource_uri,
                    details={"project": project, "kind": kind, "name": name},
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_delete_resource", project=project, resource_name=name
                )
                raise
