"""Project Management Tools - 5 tools for ArgoCD AppProject RBAC and multi-tenancy."""

from typing import Any, Dict, List, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from argocd_mcp_server.tools.base import BaseTool


class ProjectManagementTools(BaseTool):
    """Tools for managing ArgoCD AppProjects."""

    toolset_name: str = "projects"

    def register(self, mcp_instance: Any) -> None:
        """Register project management tools with FastMCP."""

        if self.should_register_tool(is_read_only=True):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="List Projects",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def list_projects(
                name_filter: Optional[str] = Field(
                    default=None,
                    description="Optional case-insensitive substring filter on project name.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """List all ArgoCD AppProjects with source repositories and destination rules."""
                await self._log_info(
                    ctx,
                    "Listing ArgoCD projects",
                    extra={"name_filter": name_filter},
                )
                return await self.mgmt_service.list_projects(name_filter=name_filter)

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Project",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_project(
                project_name: str = Field(
                    ...,
                    description="Name of the ArgoCD AppProject.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Get detailed AppProject configuration, allowed repositories, destinations, and resource restrictions."""
                await self._log_info(
                    ctx,
                    f"Getting project details for {project_name}",
                    extra={"project_name": project_name},
                )
                return await self.mgmt_service.get_project(project_name=project_name)

        if self.should_register_tool(is_read_only=False):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Create Project",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def create_project(
                project_name: str = Field(
                    ...,
                    description="Unique name for the ArgoCD AppProject.",
                ),
                description: str = Field(
                    ...,
                    description="Human-readable project description.",
                ),
                source_repos: List[str] = Field(
                    ...,
                    description="Allowed Git repository URLs or '*' wildcard.",
                ),
                destinations: List[Dict[str, str]] = Field(
                    ...,
                    description="Allowed cluster/namespace targets: [{'server': 'https://kubernetes.default.svc', 'namespace': 'prod-*'}].",
                ),
                resource_restrictions: Optional[Dict[str, Any]] = Field(
                    default=None,
                    description="Optional RBAC resource restrictions dict: {'cluster_resource_whitelist': [...], 'cluster_resource_blacklist': [...], 'namespace_resource_whitelist': [...], 'namespace_resource_blacklist': [...], 'orphaned_resources_warn': bool}.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Create a new ArgoCD AppProject with source repositories, destinations, and RBAC restrictions."""
                await self._log_info(
                    ctx,
                    f"Creating project {project_name}",
                    extra={"project_name": project_name},
                )
                return await self.mgmt_service.create_project(
                    project_name=project_name,
                    description=description,
                    source_repos=source_repos,
                    destinations=destinations,
                    resource_restrictions=resource_restrictions,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Update Project",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def update_project(
                project_name: str = Field(
                    ...,
                    description="Name of the ArgoCD AppProject to update.",
                ),
                description: Optional[str] = Field(
                    default=None,
                    description="Updated project description.",
                ),
                source_repos: Optional[List[str]] = Field(
                    default=None,
                    description="Updated list of allowed source repository URLs.",
                ),
                destinations: Optional[List[Dict[str, str]]] = Field(
                    default=None,
                    description="Updated list of allowed cluster/namespace destinations.",
                ),
                resource_restrictions: Optional[Dict[str, Any]] = Field(
                    default=None,
                    description="Updated RBAC resource restrictions dict.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Update an existing ArgoCD AppProject's description, repositories, destinations, or resource restrictions."""
                await self._log_info(
                    ctx,
                    f"Updating project {project_name}",
                    extra={"project_name": project_name},
                )
                return await self.mgmt_service.update_project(
                    project_name=project_name,
                    description=description,
                    source_repos=source_repos,
                    destinations=destinations,
                    resource_restrictions=resource_restrictions,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Delete Project",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def delete_project(
                project_name: str = Field(
                    ...,
                    description="Name of the ArgoCD AppProject to delete.",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Set True after operator confirmation to execute deletion.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Delete an ArgoCD AppProject (fails safely if applications still belong to the project)."""
                self.mgmt_service._check_write_access("project deletion")
                gate = await self.confirm_destructive_action(
                    ctx,
                    f"delete project '{project_name}'",
                    confirm=confirm,
                    impact_preview={
                        "operation": "delete_project",
                        "project_name": project_name,
                        "effect": "Deletes the ArgoCD AppProject RBAC boundary.",
                    },
                )
                if gate is not None:
                    return gate

                await self._log_warning(
                    ctx,
                    f"Deleting project {project_name}",
                    extra={"project_name": project_name},
                )
                return await self.mgmt_service.delete_project(project_name=project_name)
