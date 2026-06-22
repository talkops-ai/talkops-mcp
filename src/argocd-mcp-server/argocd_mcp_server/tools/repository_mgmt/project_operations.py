"""Project management tools for ArgoCD."""

from typing import Dict, Any, Optional, List
from pydantic import Field
from mcp.types import ToolAnnotations
from fastmcp import Context

from argocd_mcp_server.tools.base import BaseTool
from argocd_mcp_server.services.argocd_mgmt import ArgoCDManagementService
from argocd_mcp_server.exceptions import (
    ArgoCDOperationError,
    ArgoCDNotFoundError
)


class ProjectManagementTools(BaseTool):
    """Tools for managing ArgoCD projects."""
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator."""
        super().__init__(service_locator)
        # Create management service instance
        self.mgmt_service = ArgoCDManagementService(self.config)
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create ArgoCD Project",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def create_project(
            project_name: str = Field(..., min_length=1, description='Project name (must be unique)'),
            description: str = Field(..., min_length=1, description='Project description'),
            source_repos: List[str] = Field(
                ...,
                description=(
                    'List of allowed source repository URLs. Supports wildcards. '
                    'Example: ["https://github.com/org/*", "https://github.com/org/specific-repo.git"]'
                ),
            ),
            destinations: List[Dict[str, str]] = Field(
                ...,
                description=(
                    'List of allowed destination clusters and namespaces as JSON objects. '
                    'Example: [{"server": "https://kubernetes.default.svc", "namespace": "prod"}, '
                    '{"server": "https://kubernetes.default.svc", "namespace": "staging"}]'
                ),
            ),
            cluster_resource_whitelist: Optional[List[Dict[str, str]]] = Field(
                default=None,
                description=(
                    'Allowed cluster-scoped resources as JSON objects. '
                    'Example: [{"group": "apps", "kind": "Deployment"}, {"group": "", "kind": "Service"}]'
                ),
            ),
            cluster_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied cluster-scoped resources'),
            namespace_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed namespace-scoped resources'),
            namespace_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied namespace-scoped resources'),
            orphaned_resources_warn: bool = Field(default=False, description='Warn about orphaned resources'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Create a new ArgoCD project for organizing applications.

            Projects enable multi-tenancy by restricting what may be
            deployed, from which repositories, and to which clusters/namespaces.

            **WARNING: Project policies control access. Misconfigured
            source_repos or destinations can block application syncs.**

            Returns:
            - {"summary": str, "project_name": str, "source_repos": [...],
               "destinations": [...]}

            When NOT to use:
            - To update an existing project → use update_project.
            - To generate a manifest for GitOps → use generate_project_manifest.

            Common errors:
            - Project already exists: Use get_project to view it.
            """
            await ctx.info(
                f"Creating ArgoCD project: {project_name}",
                extra={'project_name': project_name, 'source_repos_count': len(source_repos)}
            )
            
            # Validate inputs
            if not source_repos:
                error_msg = "At least one source repository must be specified"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            if not destinations:
                error_msg = "At least one destination must be specified"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            try:
                result = await self.mgmt_service.create_project(
                    project_name=project_name,
                    description=description,
                    source_repos=source_repos,
                    destinations=destinations,
                    cluster_resource_whitelist=cluster_resource_whitelist,
                    cluster_resource_blacklist=cluster_resource_blacklist,
                    namespace_resource_whitelist=namespace_resource_whitelist,
                    namespace_resource_blacklist=namespace_resource_blacklist,
                    orphaned_resources_warn=orphaned_resources_warn
                )
                
                await ctx.info(
                    f"Successfully created project: {project_name}",
                    extra={'source_repos': source_repos, 'destinations': destinations}
                )
                
                summary = (
                    f"Project '{project_name}' created successfully. "
                    f"Configured with {len(source_repos)} source repository pattern(s) "
                    f"and {len(destinations)} destination(s). "
                    f"You can now create applications scoped to this project."
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDOperationError as e:
                error_msg = str(e)
                if "already exists" in error_msg.lower():
                    friendly_msg = (
                        f"Project '{project_name}' already exists in ArgoCD. "
                        f"Use 'get_project' to view its configuration or chose a different name."
                    )
                    await ctx.warning(friendly_msg)
                    raise ArgoCDOperationError(friendly_msg)
                else:
                    friendly_msg = (
                        f"Failed to create project '{project_name}': {error_msg}. "
                        f"Verify the project name is valid and all parameters are correctly specified."
                    )
                    await ctx.error(friendly_msg)
                    raise ArgoCDOperationError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Unexpected error while creating project: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List ArgoCD Projects",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def list_projects(
            name_filter: Optional[str] = Field(default=None, description='Optional project name filter'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List all ArgoCD projects.

            Use to discover available projects and their configurations.
            Optionally filter by name. Read-only.

            Returns:
            - {"summary": str, "total": int,
               "projects": [{"name": str, ...}]}

            When NOT to use:
            - To get details of one project → use get_project.
            - To create a project → use create_project.
            """
            await ctx.info(
                "Listing ArgoCD projects",
                extra={'filter': name_filter or 'none'}
            )
            
            try:
                result = await self.mgmt_service.list_projects(name_filter=name_filter)
                
                total = result.get('total', 0)
                await ctx.info(
                    f"Found {total} projects",
                    extra={'total': total}
                )
                
                if total == 0:
                    summary = (
                        "No projects found in ArgoCD. "
                        "Use 'create_project' to create a new project for organizing applications."
                    )
                else:
                    summary = f"Found {total} projects in ArgoCD."
                
                return {
                    "summary": summary,
                    **result
                }
                
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to list projects: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Update ArgoCD Project",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def update_project(
            project_name: str = Field(..., min_length=1, description='Project name'),
            description: Optional[str] = Field(default=None, description='Project description'),
            source_repos: Optional[List[str]] = Field(
                default=None,
                description=(
                    'Updated list of allowed source repository URLs. '
                    'Example: ["https://github.com/org/*"]'
                ),
            ),
            destinations: Optional[List[Dict[str, str]]] = Field(
                default=None,
                description=(
                    'Updated list of allowed destinations as JSON objects. '
                    'Example: [{"server": "https://kubernetes.default.svc", "namespace": "prod"}]'
                ),
            ),
            cluster_resource_whitelist: Optional[List[Dict[str, str]]] = Field(
                default=None,
                description=(
                    'Updated allowed cluster-scoped resources as JSON objects. '
                    'Example: [{"group": "apps", "kind": "Deployment"}]'
                ),
            ),
            cluster_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied cluster-scoped resources'),
            namespace_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed namespace-scoped resources'),
            namespace_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied namespace-scoped resources'),
            orphaned_resources_warn: Optional[bool] = Field(default=None, description='Warn about orphaned resources'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Update an existing ArgoCD project's configuration.

            Use to modify allowed destinations, source repositories,
            or resource restrictions on an existing project.

            **WARNING: Changing source_repos or destinations may break
            existing applications scoped to this project.**

            Returns:
            - {"summary": str, "project_name": str}

            When NOT to use:
            - To create a new project → use create_project.
            - To delete a project → use delete_project.
            """
            await ctx.info(
                f"Updating project: {project_name}",
                extra={'project_name': project_name}
            )
            
            try:
                result = await self.mgmt_service.update_project(
                    project_name=project_name,
                    description=description,
                    source_repos=source_repos,
                    destinations=destinations,
                    cluster_resource_whitelist=cluster_resource_whitelist,
                    cluster_resource_blacklist=cluster_resource_blacklist,
                    namespace_resource_whitelist=namespace_resource_whitelist,
                    namespace_resource_blacklist=namespace_resource_blacklist,
                    orphaned_resources_warn=orphaned_resources_warn
                )
                
                await ctx.info(f"Project updated successfully: {project_name}")
                
                summary = f"Project '{project_name}' has been updated successfully in ArgoCD."
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDNotFoundError:
                friendly_msg = (
                    f"Project '{project_name}' not found in ArgoCD. "
                    f"Cannot update a non-existent project."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDNotFoundError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to update project: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get ArgoCD Project Details",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def get_project(
            project_name: str = Field(..., min_length=1, description='Project name'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get detailed information about a specific ArgoCD project.

            Use to view a project's full configuration including source
            repositories, destinations, and resource restrictions. Read-only.

            Returns:
            - {"summary": str, "name": str, "source_repos": [...],
               "destinations": [...], ...}

            When NOT to use:
            - To list all projects → use list_projects.
            - To update a project → use update_project.
            """
            await ctx.info(
                f"Getting project details: {project_name}",
                extra={'project_name': project_name}
            )
            
            try:
                result = await self.mgmt_service.get_project(project_name=project_name)
                
                source_repos_count = len(result.get('source_repos', []))
                destinations_count = len(result.get('destinations', []))
                
                await ctx.info(
                    f"Project found: {project_name}",
                    extra={'source_repos': source_repos_count, 'destinations': destinations_count}
                )
                
                summary = (
                    f"Project '{project_name}' - "
                    f"{source_repos_count} source repository pattern(s), "
                    f"{destinations_count} destination(s)"
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDNotFoundError:
                friendly_msg = (
                    f"Project '{project_name}' not found in ArgoCD. "
                    f"Use 'list_projects' to see all available projects, or "
                    f"use 'create_project' to create it."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDNotFoundError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to get project details: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete ArgoCD Project",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def delete_project(
            project_name: str = Field(..., min_length=1, description='Project name to delete'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Delete an ArgoCD project.

            Use when permanently removing a project. All applications
            in the project must be deleted first.

            **WARNING: DESTRUCTIVE — Cannot be undone. Applications scoped
            to this project will need to be recreated under a different
            project.**

            Returns:
            - {"summary": str, "status": str}

            When NOT to use:
            - To update a project → use update_project.

            Common errors:
            - Project has applications: Delete all apps in the project first.
            """
            await ctx.warning(
                f"Deleting project: {project_name}",
                extra={'project_name': project_name}
            )
            
            try:
                result = await self.mgmt_service.delete_project(project_name=project_name)
                
                await ctx.info(f"Project deleted successfully: {project_name}")
                
                summary = (
                    f"Project '{project_name}' has been deleted from ArgoCD. "
                    f"All applications that were scoped to this project should be recreated "
                    f"under a different project or the default project."
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDNotFoundError:
                friendly_msg = (
                    f"Project '{project_name}' not found in ArgoCD. "
                    f"It may have already been deleted. No action needed."
                )
                await ctx.warning(friendly_msg)
                raise ArgoCDNotFoundError(friendly_msg)
            except ArgoCDOperationError as e:
                error_msg = str(e)
                if "applications" in error_msg.lower():
                    friendly_msg = (
                        f"Cannot delete project '{project_name}' because it still has applications. "
                        f"Delete all applications in this project first, then try again."
                    )
                else:
                    friendly_msg = f"Failed to delete project: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to delete project: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Generate Project Manifest",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def generate_project_manifest(
            project_name: str = Field(..., min_length=1, description='Project name'),
            description: str = Field(..., min_length=1, description='Project description'),
            source_repos: List[str] = Field(
                ...,
                description=(
                    'List of allowed source repository URLs. Supports wildcards. '
                    'Example: ["https://github.com/org/*"]'
                ),
            ),
            destinations: List[Dict[str, str]] = Field(
                ...,
                description=(
                    'List of allowed destination clusters and namespaces as JSON objects. '
                    'Example: [{"server": "https://kubernetes.default.svc", "namespace": "prod"}]'
                ),
            ),
            namespace: str = Field(default="argocd", description='Kubernetes namespace for the project'),
            cluster_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed cluster-scoped resources'),
            cluster_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied cluster-scoped resources'),
            namespace_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed namespace-scoped resources'),
            namespace_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied namespace-scoped resources'),
            orphaned_resources_warn: bool = Field(default=False, description='Warn about orphaned resources'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate an AppProject manifest for declarative project management.

            Generates a YAML manifest that can be applied via kubectl or
            committed to Git for GitOps workflows. Recommended approach
            for production environments. Read-only — does not apply anything.

            Returns:
            - {"summary": str, "manifest": str, "project_name": str}

            When NOT to use:
            - To create via API → use create_project.
            """
            await ctx.info(
                f"Generating AppProject manifest: {project_name}",
                extra={'project_name': project_name, 'namespace': namespace}
            )
            
            # Validate inputs
            if not source_repos:
                error_msg = "At least one source repository must be specified"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            if not destinations:
                error_msg = "At least one destination must be specified"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            try:
                result = await self.mgmt_service.generate_project_manifest(
                    project_name=project_name,
                    description=description,
                    source_repos=source_repos,
                    destinations=destinations,
                    namespace=namespace,
                    cluster_resource_whitelist=cluster_resource_whitelist,
                    cluster_resource_blacklist=cluster_resource_blacklist,
                    namespace_resource_whitelist=namespace_resource_whitelist,
                    namespace_resource_blacklist=namespace_resource_blacklist,
                    orphaned_resources_warn=orphaned_resources_warn
                )
                
                await ctx.info(
                    f"Generated AppProject manifest: {project_name}",
                    extra={'namespace': namespace}
                )
                
                summary = (
                    f"Generated AppProject manifest for '{project_name}' in namespace '{namespace}'. "
                    f"Apply this manifest with: kubectl apply -f <manifest-file>.yaml"
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to generate project manifest: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
