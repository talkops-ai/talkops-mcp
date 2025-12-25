"""Project management tools for ArgoCD."""

from typing import Dict, Any, Optional, List
from pydantic import Field
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
        
        @mcp_instance.tool()
        async def create_project(
            project_name: str = Field(..., min_length=1, description='Project name (must be unique)'),
            description: str = Field(..., min_length=1, description='Project description'),
            source_repos: List[str] = Field(..., description='List of source repository URLs (supports wildcards like https://github.com/org/*)'),
            destinations: List[Dict[str, str]] = Field(..., description='List of destination clusters and namespaces, e.g. [{"server": "https://kubernetes.default.svc", "namespace": "prod"}]'),
            cluster_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed cluster-scoped resources, e.g. [{"group": "apps", "kind": "Deployment"}]'),
            cluster_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied cluster-scoped resources'),
            namespace_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed namespace-scoped resources'),
            namespace_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied namespace-scoped resources'),
            orphaned_resources_warn: bool = Field(default=False, description='Warn about orphaned resources'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """
            Create a new ArgoCD project for organizing applications.
            
            Projects provide a logical grouping of ArgoCD applications and enable
            multi-tenancy by restricting what may be deployed and where. This tool
            creates projects via the ArgoCD REST API.
            
            Args:
                project_name: Unique name for the project
                description: Description of the project's purpose
                source_repos: List of allowed Git repository URLs (supports wildcards)
                destinations: Allowed deployment destinations (cluster + namespace pairs)
                cluster_resource_whitelist: Restrict which cluster-scoped resources can be deployed
                cluster_resource_blacklist: Deny specific cluster-scoped resources
                namespace_resource_whitelist: Restrict which namespace-scoped resources can be deployed
                namespace_resource_blacklist: Deny specific namespace-scoped resources
                orphaned_resources_warn: Enable warnings for orphaned Kubernetes resources
            
            Returns:
                Project creation result with configuration details
                
            Examples:
                # Team-based project
                create_project(
                    project_name="team-frontend",
                    description="Frontend team project",
                    source_repos=["https://github.com/myorg/frontend-*"],
                    destinations=[{"server": "https://kubernetes.default.svc", "namespace": "frontend-*"}]
                )
                
                # Production project with strict controls
                create_project(
                    project_name="production",
                    description="Production environment",
                    source_repos=["https://github.com/myorg/prod-*"],
                    destinations=[{"server": "https://prod-cluster.example.com", "namespace": "prod-*"}],
                    cluster_resource_whitelist=[
                        {"group": "apps", "kind": "Deployment"},
                        {"group": "", "kind": "Service"}
                    ]
                )
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
        
        @mcp_instance.tool()
        async def list_projects(
            name_filter: Optional[str] = Field(default=None, description='Optional project name filter'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """
            List all ArgoCD projects.
            
            This tool retrieves all projects currently registered in ArgoCD,
            optionally filtered by name. Useful for discovering available
            projects and monitoring project configurations.
            
            Args:
                name_filter: Optional name filter to search for specific projects
            
            Returns:
                List of projects with their configurations
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
        
        @mcp_instance.tool()
        async def get_project(
            project_name: str = Field(..., min_length=1, description='Project name'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """
            Get detailed information about a specific ArgoCD project.
            
            This tool retrieves complete configuration details for a project,
            including source repositories, destinations, and resource restrictions.
            
            Args:
                project_name: Name of the project to retrieve
            
            Returns:
                Project details including full configuration
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
        
        @mcp_instance.tool()
        async def delete_project(
            project_name: str = Field(..., min_length=1, description='Project name to delete'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """
            Delete an ArgoCD project.
            
            This tool removes a project from ArgoCD. Note: You cannot delete
            a project that still has applications. Delete all applications
            in the project first.
            
            Args:
                project_name: Name of the project to delete
            
            Returns:
                Deletion result
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
        
        @mcp_instance.tool()
        async def generate_project_manifest(
            project_name: str = Field(..., min_length=1, description='Project name'),
            description: str = Field(..., min_length=1, description='Project description'),
            source_repos: List[str] = Field(..., description='List of source repository URLs (supports wildcards)'),
            destinations: List[Dict[str, str]] = Field(..., description='List of destination clusters and namespaces'),
            namespace: str = Field(default="argocd", description='Kubernetes namespace for the project'),
            cluster_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed cluster-scoped resources'),
            cluster_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied cluster-scoped resources'),
            namespace_resource_whitelist: Optional[List[Dict[str, str]]] = Field(default=None, description='Allowed namespace-scoped resources'),
            namespace_resource_blacklist: Optional[List[Dict[str, str]]] = Field(default=None, description='Denied namespace-scoped resources'),
            orphaned_resources_warn: bool = Field(default=False, description='Warn about orphaned resources'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """
            Generate a Kubernetes AppProject manifest for declarative project management.
            
            This tool generates an AppProject YAML manifest that can be applied
            via kubectl or committed to Git for GitOps workflows. This is the
            recommended approach for production environments.
            
            Args:
                project_name: Unique name for the project
                description: Description of the project's purpose
                source_repos: List of allowed Git repository URLs (supports wildcards)
                destinations: Allowed deployment destinations 
                namespace: Kubernetes namespace (default: argocd)
                cluster_resource_whitelist: Allowed cluster-scoped resources
                cluster_resource_blacklist: Denied cluster-scoped resources
                namespace_resource_whitelist: Allowed namespace-scoped resources
                namespace_resource_blacklist: Denied namespace-scoped resources
                orphaned_resources_warn: Enable warnings for orphaned resources
            
            Returns:
                Kubernetes AppProject manifest (YAML-ready)
                
            Examples:
                # Generate manifest for production project
                generate_project_manifest(
                    project_name="production",
                    description="Production environment",
                    source_repos=["https://github.com/myorg/prod-*"],
                    destinations=[{"server": "https://prod-cluster.example.com", "namespace": "prod-*"}]
                )
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
