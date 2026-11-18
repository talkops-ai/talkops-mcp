"""Application Management Tools - 7 tools for application lifecycle operations."""

from typing import Any, Dict, Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from argocd_mcp_server.tools.base import BaseTool


class ApplicationManagerTools(BaseTool):
    """Tools for managing ArgoCD applications."""

    toolset_name: str = "applications"

    def register(self, mcp_instance: Any) -> None:
        """Register application management tools with FastMCP."""

        if self.should_register_tool(is_read_only=True):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="List Applications",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def list_applications(
                cluster: Optional[str] = Field(
                    default=None,
                    description="Filter by destination cluster name or server URL substring.",
                ),
                namespace: Optional[str] = Field(
                    default=None,
                    description="Filter by destination Kubernetes namespace.",
                ),
                project: Optional[str] = Field(
                    default=None,
                    description="Filter by ArgoCD AppProject name.",
                ),
                sync_status: Optional[str] = Field(
                    default=None,
                    description="Filter by sync status: Synced, OutOfSync, or Unknown.",
                ),
                health_status: Optional[str] = Field(
                    default=None,
                    description="Filter by health status: Healthy, Progressing, Degraded, Suspended, Missing, or Unknown.",
                ),
                limit: int = Field(
                    default=50,
                    ge=1,
                    le=200,
                    description="Maximum number of applications to return (1-200).",
                ),
                offset: int = Field(
                    default=0,
                    ge=0,
                    description="Pagination offset (0-based).",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """List ArgoCD applications with optional filtering and pagination."""
                await self._log_info(
                    ctx,
                    "Listing ArgoCD applications",
                    extra={"cluster": cluster, "project": project, "sync_status": sync_status},
                )
                return await self.argocd_service.list_applications(
                    cluster=cluster,
                    namespace=namespace,
                    project_filter=project,
                    status_filter=sync_status,
                    health_filter=health_status,
                    limit=limit,
                    offset=offset,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Application Details",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_application_details(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application.",
                ),
                detail_level: Literal["summary", "full"] = Field(
                    default="summary",
                    description="Response detail level: 'summary' (problem resources + recent 5 history entries) or 'full' (all resources, history, and conditions).",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Get application sync/health state, managed resources, sync policy, and deployment history with history IDs."""
                await self._log_info(
                    ctx,
                    f"Getting application details for {app_name}",
                    extra={"app_name": app_name, "detail_level": detail_level},
                )
                return await self.argocd_service.get_application_details(
                    app_name=app_name,
                    detail_level=detail_level,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Application Resource Tree",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_application_resource_tree(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Get the Kubernetes resource hierarchy (Deployments, ReplicaSets, Pods, Services) for an application."""
                await self._log_info(
                    ctx,
                    f"Fetching resource tree for {app_name}",
                    extra={"app_name": app_name},
                )
                return await self.argocd_service.get_application_resource_tree(
                    app_name=app_name,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Application Events",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_application_events(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application.",
                ),
                limit: int = Field(
                    default=50,
                    ge=1,
                    le=200,
                    description="Maximum number of recent events to return (1-200).",
                ),
                warnings_only: bool = Field(
                    default=False,
                    description="If True, return only Warning events.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Get recent Kubernetes events for an application sorted newest first."""
                await self._log_info(
                    ctx,
                    f"Getting events for {app_name}",
                    extra={"app_name": app_name, "warnings_only": warnings_only},
                )
                return await self.argocd_service.get_application_events(
                    app_name=app_name,
                    limit=limit,
                    warnings_only=warnings_only,
                )

        if self.should_register_tool(is_read_only=False):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Create Application",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def create_application(
                app_name: str = Field(
                    ...,
                    description="Unique name for the ArgoCD application.",
                ),
                project: str = Field(
                    ...,
                    description="ArgoCD AppProject name (e.g. 'default').",
                ),
                repo_url: str = Field(
                    ...,
                    description="Git repository URL containing application manifests.",
                ),
                path: str = Field(
                    ...,
                    description="Relative path within the Git repository to manifests/chart.",
                ),
                destination_namespace: str = Field(
                    ...,
                    description="Target Kubernetes namespace for deployment.",
                ),
                target_revision: str = Field(
                    default="HEAD",
                    description="Git branch, tag, or commit SHA to track.",
                ),
                destination_server: str = Field(
                    default="https://kubernetes.default.svc",
                    description="Target Kubernetes cluster API server URL.",
                ),
                sync_policy: Optional[Dict[str, Any]] = Field(
                    default=None,
                    description="Optional sync policy dict: {'automated': bool, 'prune': bool, 'self_heal': bool, 'create_namespace': bool}.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Create a new ArgoCD application tracking a Git repository path."""
                await self._log_info(
                    ctx,
                    f"Creating application {app_name}",
                    extra={"app_name": app_name, "project": project, "repo_url": repo_url},
                )
                return await self.argocd_service.create_application(
                    app_name=app_name,
                    project=project,
                    repo_url=repo_url,
                    path=path,
                    destination_namespace=destination_namespace,
                    target_revision=target_revision,
                    destination_server=destination_server,
                    sync_policy=sync_policy,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Update Application",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def update_application(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application to update.",
                ),
                target_revision: Optional[str] = Field(
                    default=None,
                    description="New Git branch, tag, or commit SHA to track.",
                ),
                sync_policy: Optional[Dict[str, Any]] = Field(
                    default=None,
                    description="Updated sync policy dict: {'automated': bool, 'prune': bool, 'self_heal': bool, 'create_namespace': bool}.",
                ),
                path: Optional[str] = Field(
                    default=None,
                    description="Updated manifest path in the Git repository.",
                ),
                destination_namespace: Optional[str] = Field(
                    default=None,
                    description="Updated target Kubernetes namespace.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Update an existing ArgoCD application's revision, path, namespace, or sync policy."""
                await self._log_info(
                    ctx,
                    f"Updating application {app_name}",
                    extra={"app_name": app_name, "target_revision": target_revision},
                )
                return await self.argocd_service.update_application(
                    app_name=app_name,
                    target_revision=target_revision,
                    sync_policy=sync_policy,
                    path=path,
                    destination_namespace=destination_namespace,
                )

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Delete Application",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def delete_application(
                app_name: str = Field(
                    ...,
                    description="Name of the ArgoCD application to delete.",
                ),
                cascade: bool = Field(
                    default=True,
                    description="If True, also deletes all Kubernetes resources managed by this application.",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Set True after operator confirmation to execute deletion.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Delete an ArgoCD application and optionally cascade-delete its cluster resources."""
                self.argocd_service._check_write_access("application deletion")
                gate = await self.confirm_destructive_action(
                    ctx,
                    f"delete application '{app_name}' (cascade={cascade})",
                    confirm=confirm,
                    impact_preview={
                        "operation": "delete_application",
                        "app_name": app_name,
                        "cascade": cascade,
                        "effect": (
                            "Deletes ArgoCD application AND all managed Kubernetes resources"
                            if cascade
                            else "Deletes ArgoCD application definition only (orphans cluster resources)"
                        ),
                    },
                )
                if gate is not None:
                    return gate

                await self._log_warning(
                    ctx,
                    f"Deleting application {app_name} (cascade={cascade})",
                    extra={"app_name": app_name, "cascade": cascade},
                )
                return await self.argocd_service.delete_application(
                    app_name=app_name,
                    cascade=cascade,
                )
