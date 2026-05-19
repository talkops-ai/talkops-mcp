"""Kargo project tools."""

from typing import Dict, Any, List, Literal, Optional
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError
from kargo_mcp_server.tools.base import BaseTool
from kargo_mcp_server.models.project import ProjectSpec, PromotionPolicy

PROJECT_ACTIONS = Literal["create", "update", "delete", "list", "get"]


class ProjectTools(BaseTool):
    """Tools for managing Kargo projects."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_project_mgmt(
            action: PROJECT_ACTIONS = Field(..., description="Action to perform: create, update, delete, list, get"),
            name: Optional[str] = Field(default=None, description="Project name (required for create, update, delete, get)"),
            auto_promotion: Optional[bool] = Field(default=None, description="Enable auto-promotion (for create, update)"),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Any:
            """Manage Kargo projects and their lifecycle.

            Use this tool to create, update, delete, list, or retrieve Kargo projects. 
            A Kargo Project represents an organizational boundary that maps to a Kubernetes namespace.
            Always use this tool to verify a project exists before performing operations on stages, warehouses, or freight within it.

            Actions:
            - list: Discover all available Kargo projects.
            - get: Retrieve configuration details for a specific project.
            - create: Create a new project (can optionally enable auto-promotion).
            - update: Modify an existing project's settings.
            - delete: Remove a project entirely.
            
            Args:
                action: Operation to perform (create, update, delete, list, get)
                name: Project name
                auto_promotion: Whether to enable auto-promotion for this project
            """
            await ctx.info(f"Executing project management action: {action}")

            try:
                if action == "list":
                    projects = await self.kargo_service.list_projects()
                    if not projects:
                        return [{"message": "No projects found. Next step: Please verify your cluster configuration, or create a new Kargo project."}]
                    return [p.model_dump() for p in projects]

                if not name:
                    raise ValueError(f"Action '{action}' requires 'name' parameter.")

                if action == "get":
                    return await self.kargo_service.get_project(name)

                if action == "delete":
                    return await self.kargo_service.delete_project(name)

                if action in ("create", "update"):
                    spec = None
                    if auto_promotion is not None:
                        spec = ProjectSpec.model_validate(
                            {"promotionPolicy": {"autoPromotionEnabled": auto_promotion}}
                        )
                    elif action == "update":
                        raise ValueError("Update requires at least one field to update (e.g. auto_promotion)")

                    if action == "create":
                        project = await self.kargo_service.create_project(name, spec)
                    else:
                        if spec is None:
                            raise ValueError("Update requires at least one field to update (e.g. auto_promotion)")
                        project = await self.kargo_service.update_project(name, spec)

                    return project.model_dump(by_alias=True)

            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to perform '{action}' on project '{name or 'all'}': {error_msg}. "
                    "Please verify your Kargo authentication token and ensure the "
                    "Kargo API server is reachable."
                )
                await ctx.error(friendly_msg)
                raise KargoOperationError(friendly_msg)
