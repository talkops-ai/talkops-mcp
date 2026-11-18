"""Kargo Stage verification and AnalysisTemplate tools (Toolset: verification)."""

from typing import Any, Dict, Literal, Optional
import yaml
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from kargo_mcp_server.exceptions.custom import KargoValidationError
from kargo_mcp_server.models.schemas import ExecutionResult
from kargo_mcp_server.tools.base import BaseTool, confirm_destructive_action


class VerificationTools(BaseTool):
    """Tools for managing Kargo Stage verification runs and Argo Rollouts AnalysisTemplates."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register verification tools with FastMCP."""
        if not self.should_register("verification", is_write=True):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Apply Kargo Verification AnalysisTemplate",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_apply_analysis_template(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            name: str = Field(..., min_length=1, description="AnalysisTemplate or ClusterAnalysisTemplate name."),
            spec: Dict[str, Any] = Field(
                ...,
                description=(
                    "AnalysisTemplate spec containing 'metrics' (Job, Web, or Prometheus metrics) "
                    "and optional 'args'."
                ),
            ),
            kind: Literal["AnalysisTemplate", "ClusterAnalysisTemplate"] = Field(
                default="AnalysisTemplate",
                description="Template scope ('AnalysisTemplate' for project or 'ClusterAnalysisTemplate' for cluster).",
            ),
            dry_run: bool = Field(
                default=True,
                description="Preview the AnalysisTemplate YAML manifest without applying (default: True).",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Create or update an Argo Rollouts AnalysisTemplate or ClusterAnalysisTemplate for Kargo Stage verification."""
            self.check_write_access("kargo_apply_analysis_template")
            resource_uri = f"kargo://projects/{project}/analysis-templates"

            try:
                if not isinstance(spec, dict) or not spec.get("metrics"):
                    raise KargoValidationError(
                        "AnalysisTemplate 'spec' must contain a non-empty 'metrics' list."
                    )

                metadata: Dict[str, Any] = {"name": name}
                if kind == "AnalysisTemplate":
                    metadata["namespace"] = project

                manifest_dict = {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": kind,
                    "metadata": metadata,
                    "spec": spec,
                }
                manifest_yaml = yaml.dump(manifest_dict, default_flow_style=False)
                details = {
                    "project": project,
                    "name": name,
                    "kind": kind,
                    "metrics_count": len(spec.get("metrics") or []),
                }

                if dry_run:
                    return ExecutionResult(
                        status="preview",
                        summary=f"Previewed {kind} '{name}' (dry_run=True). Re-run with dry_run=False to apply.",
                        dry_run=True,
                        manifest=manifest_yaml,
                        resource_uri=resource_uri,
                        details=details,
                    )

                await self.kargo_service.upsert_analysis_template(
                    project=project,
                    name=name,
                    spec=spec,
                    kind=kind,
                )
                return ExecutionResult(
                    status="success",
                    summary=f"Applied {kind} '{name}' in project '{project}'.",
                    dry_run=False,
                    manifest=manifest_yaml,
                    resource_uri=resource_uri,
                    details=details,
                )
            except Exception as exc:
                self.handle_error(
                    exc, "kargo_apply_analysis_template", project=project, resource_name=name
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Manage Kargo Stage Verification",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def kargo_manage_verification(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            stage: str = Field(
                ...,
                min_length=1,
                description="Target Stage name (or project reference when action='delete_template').",
            ),
            action: Literal["reverify", "abort", "delete_template"] = Field(
                ...,
                description=(
                    "Action: 'reverify' (re-run verification for current Freight), "
                    "'abort' (abort in-progress verification), or 'delete_template' (delete AnalysisTemplate)."
                ),
            ),
            template_name: Optional[str] = Field(
                default=None,
                description="AnalysisTemplate name when action='delete_template'.",
            ),
            confirm: bool = Field(
                default=False,
                description="Confirm aborting verification or deleting an AnalysisTemplate when interactive elicitation is unavailable.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> ExecutionResult:
            """Re-run (reverify) or abort a Stage's verification AnalysisRun, or delete an AnalysisTemplate."""
            self.check_write_access("kargo_manage_verification")
            resource_uri = f"kargo://projects/{project}/stages/{stage}"

            try:
                if action == "reverify":
                    updated = await self.kargo_service.reverify_stage(project, stage)
                    return ExecutionResult(
                        status="success",
                        summary=f"Triggered re-verification on Stage '{stage}' in project '{project}'.",
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={
                            "project": project,
                            "stage": updated.metadata.name,
                            "current_freight": updated.get_current_freight_id(),
                            "action": "reverify",
                        },
                    )

                if action == "abort":
                    if not await confirm_destructive_action(
                        ctx,
                        action_summary=f"Abort active verification on Stage '{stage}' in project '{project}'",
                        confirm=confirm,
                        resource_uri=resource_uri,
                        details={"project": project, "stage": stage, "action": "abort"},
                    ):
                        return ExecutionResult(
                            status="cancelled",
                            summary=(
                                f"Confirmation required to abort verification on Stage '{stage}'. "
                                "Re-run with confirm=True after user approval."
                            ),
                            dry_run=False,
                            resource_uri=resource_uri,
                            details={
                                "project": project,
                                "stage": stage,
                                "action": "abort",
                                "requires_confirmation": True,
                            },
                        )

                    updated = await self.kargo_service.abort_stage_verification(project, stage)
                    return ExecutionResult(
                        status="success",
                        summary=f"Aborted verification on Stage '{stage}' in project '{project}'.",
                        dry_run=False,
                        resource_uri=resource_uri,
                        details={
                            "project": project,
                            "stage": updated.metadata.name,
                            "action": "abort",
                        },
                    )

                # action == "delete_template"
                if not template_name:
                    raise KargoValidationError(
                        "'template_name' is required when action='delete_template'."
                    )
                if not await confirm_destructive_action(
                    ctx,
                    action_summary=f"Delete AnalysisTemplate '{template_name}' in project '{project}'",
                    confirm=confirm,
                    resource_uri=f"kargo://projects/{project}/analysis-templates",
                    details={"project": project, "template_name": template_name},
                ):
                    return ExecutionResult(
                        status="cancelled",
                        summary=(
                            f"Confirmation required to delete AnalysisTemplate '{template_name}'. "
                            "Re-run with confirm=True after user approval."
                        ),
                        dry_run=False,
                        resource_uri=f"kargo://projects/{project}/analysis-templates",
                        details={
                            "project": project,
                            "template_name": template_name,
                            "requires_confirmation": True,
                        },
                    )

                await self.kargo_service.delete_analysis_template(
                    project, template_name, kind="AnalysisTemplate"
                )
                return ExecutionResult(
                    status="success",
                    summary=f"Deleted AnalysisTemplate '{template_name}' in project '{project}'.",
                    dry_run=False,
                    resource_uri=f"kargo://projects/{project}/analysis-templates",
                    details={"project": project, "template_name": template_name},
                )
            except Exception as exc:
                self.handle_error(
                    exc,
                    "kargo_manage_verification",
                    project=project,
                    resource_name=template_name or stage,
                )
                raise
