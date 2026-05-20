"""Kargo promotion task tools.

Provides intelligent PromotionTask creation via preset-based workflows
or custom step definitions. Users who are new to Kargo can select a
preset (e.g., "gitops-image-update") and provide a few parameters to
get a fully functional promotion pipeline, while advanced users retain
full control via custom_steps.
"""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError, KargoValidationError
from kargo_mcp_server.tools.base import BaseTool
from kargo_mcp_server.utils.promotion_task_spec_builder import (
    build_promotion_task_spec,
    AVAILABLE_PRESETS,
)


class PromotionTaskTools(BaseTool):
    """Tools for managing Kargo promotion tasks."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_promotion_task_mgmt(
            action: Literal["list", "get", "upsert"],
            project: str = Field(..., min_length=1, description="Kargo project name"),
            task_name: Optional[str] = Field(
                None,
                description="PromotionTask name (required for get, upsert)",
            ),
            preset: Optional[str] = Field(
                None,
                description=(
                    "Built-in workflow preset for upsert. Available presets: "
                    "gitops-image-update (YAML values update), "
                    "gitops-kustomize (Kustomize overlay workflow), "
                    "gitops-helm-template (Helm chart rendering). "
                    "Mutually exclusive with custom_steps."
                ),
            ),
            custom_steps: Optional[List[Dict[str, Any]]] = Field(
                None,
                description=(
                    "Raw promotion steps for advanced use cases (mutually exclusive "
                    "with preset). Each step dict should have 'uses' (step runner name) "
                    "and 'config' (step configuration)."
                ),
            ),
            git_repo_url: Optional[str] = Field(
                None,
                description="Git repository URL to clone during promotion (used with presets)",
            ),
            image_repo_url: Optional[str] = Field(
                None,
                description="Container image repository URL for image tag tracking (used with presets)",
            ),
            target_branch: Optional[str] = Field(
                None,
                description="Git branch to clone and push to (default: 'main')",
            ),
            values_path_pattern: Optional[str] = Field(
                None,
                description=(
                    "Path to values.yaml relative to repo root, may include Kargo expressions "
                    "(default: 'env/${{ ctx.stage }}/values.yaml'). Used by gitops-image-update preset."
                ),
            ),
            image_key: Optional[str] = Field(
                None,
                description="YAML key path for the image tag (default: 'image.tag'). Used by gitops-image-update preset.",
            ),
            argocd_app_name_pattern: Optional[str] = Field(
                None,
                description=(
                    "ArgoCD Application name, may include Kargo expressions "
                    "(default: '${{ ctx.project }}-${{ ctx.stage }}')"
                ),
            ),
            kustomization_path_pattern: Optional[str] = Field(
                None,
                description="Path to kustomization overlay directory (required for gitops-kustomize preset)",
            ),
            chart_path_pattern: Optional[str] = Field(
                None,
                description="Path to Helm chart directory (required for gitops-helm-template preset)",
            ),
            extra_vars: Optional[List[Dict[str, str]]] = Field(
                None,
                description="Additional PromotionTask variables as [{'name': '...', 'value': '...'}]",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Manage Kargo PromotionTask CRDs.

            Use this tool to list, retrieve, or create/update Kargo promotion tasks.
            A PromotionTask defines the steps executed during a promotion to a stage.

            Actions:
            - list: Discover all promotion tasks in a project.
            - get: Retrieve configuration details for a specific promotion task.
            - upsert: Create or update a promotion task using a preset workflow or custom steps (requires allow_write=true).

            Upsert with preset — create a GitOps image update promotion task:
                action: "upsert"
                project: "my-project"
                task_name: "promote"
                preset: "gitops-image-update"
                git_repo_url: "https://github.com/org/repo.git"
                image_repo_url: "ghcr.io/org/app"
                argocd_app_name_pattern: "myapp-${{ ctx.stage }}"

            Upsert with custom steps — full control:
                action: "upsert"
                project: "my-project"
                task_name: "custom-promote"
                custom_steps: [
                    {"uses": "git-clone", "config": {"repoURL": "..."}},
                    {"uses": "yaml-update", "config": {"path": "...", "updates": [...]}}
                ]
            """
            if action == "upsert" and not self.config.allow_write:
                raise KargoOperationError(
                    "Write operations are disabled. Set MCP_ALLOW_WRITE=true to enable."
                )

            if action in ["get", "upsert"] and not task_name:
                raise KargoValidationError(f"'task_name' is required for action '{action}'")

            if action == "list":
                await ctx.info(
                    f"Listing promotion tasks for project '{project}'",
                    extra={'project': project}
                )
                try:
                    tasks = await self.kargo_service.list_promotion_tasks(project)
                    await ctx.info(
                        f"Found {len(tasks)} promotion tasks",
                        extra={'project': project, 'count': len(tasks)}
                    )
                    if not tasks:
                        return [{
                            "message": (
                                f"No promotion tasks found in project '{project}'. "
                                "Use 'kargo_promotion_task_mgmt' with action 'upsert' "
                                "and a preset to create one."
                            )
                        }]
                    return tasks
                except Exception as e:
                    friendly_msg = (
                        f"Failed to list promotion tasks: {str(e)}. "
                        "Use 'kargo_project_mgmt' to verify the project exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "get":
                if not isinstance(task_name, str):
                    raise KargoValidationError("task_name must be a string")
                await ctx.info(
                    f"Fetching promotion task '{task_name}' in project '{project}'",
                    extra={'project': project, 'task_name': task_name}
                )
                try:
                    task = await self.kargo_service.get_promotion_task(project, task_name)
                    await ctx.info(f"Successfully retrieved promotion task '{task_name}'")
                    return task
                except Exception as e:
                    friendly_msg = (
                        f"Failed to get promotion task '{task_name}': {str(e)}. "
                        "Use 'kargo_promotion_task_mgmt' with action 'list' to verify the task exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "upsert":
                if not isinstance(task_name, str):
                    raise KargoValidationError("task_name must be a string")

                # Normalize pydantic FieldInfo defaults to None for clean handling.
                # When tool is called directly (tests, programmatic use) instead of
                # through FastMCP's parameter injection, Field(None, ...) returns a
                # FieldInfo object rather than None.
                _preset = preset if isinstance(preset, str) else None
                _custom_steps = custom_steps if isinstance(custom_steps, list) else None
                _git_repo_url = git_repo_url if isinstance(git_repo_url, str) else None
                _image_repo_url = image_repo_url if isinstance(image_repo_url, str) else None
                _target_branch = target_branch if isinstance(target_branch, str) else "main"
                _values_path = values_path_pattern if isinstance(values_path_pattern, str) else "env/${{ ctx.stage }}/values.yaml"
                _image_key = image_key if isinstance(image_key, str) else "image.tag"
                _argocd_app = argocd_app_name_pattern if isinstance(argocd_app_name_pattern, str) else None
                _kustomization_path = kustomization_path_pattern if isinstance(kustomization_path_pattern, str) else None
                _chart_path = chart_path_pattern if isinstance(chart_path_pattern, str) else None
                _extra_vars = extra_vars if isinstance(extra_vars, list) else None

                # Log what mode we're using
                mode = "preset" if _preset else "custom_steps"
                await ctx.info(
                    f"Building promotion task spec for '{task_name}' using {mode}",
                    extra={
                        'project': project,
                        'task_name': task_name,
                        'mode': mode,
                        'preset': _preset,
                    }
                )

                # Build the spec from user-friendly parameters
                spec = build_promotion_task_spec(
                    preset=_preset,
                    custom_steps=_custom_steps,
                    git_repo_url=_git_repo_url,
                    image_repo_url=_image_repo_url,
                    target_branch=_target_branch,
                    values_path_pattern=_values_path,
                    image_key=_image_key,
                    argocd_app_name_pattern=_argocd_app,
                    kustomization_path_pattern=_kustomization_path,
                    chart_path_pattern=_chart_path,
                    extra_vars=_extra_vars,
                )

                await ctx.info(
                    f"Upserting promotion task '{task_name}' in project '{project}'",
                    extra={'project': project, 'task_name': task_name}
                )
                try:
                    task = await self.kargo_service.upsert_promotion_task(
                        project, task_name, spec
                    )
                    msg = f"Successfully upserted promotion task '{task_name}'"
                    await ctx.info(msg)
                    return {
                        "name": task.metadata.name,
                        "namespace": task.metadata.namespace,
                    }
                except KargoValidationError:
                    raise
                except Exception as e:
                    friendly_msg = (
                        f"Failed to upsert promotion task '{task_name}': {str(e)}. "
                        "Verify that the preset parameters or custom steps are correct."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            return {}
