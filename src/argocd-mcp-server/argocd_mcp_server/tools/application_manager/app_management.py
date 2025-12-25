"""Application management tools."""

from typing import Dict, Any, Optional
from pydantic import Field
from fastmcp import Context

from argocd_mcp_server.tools.base import BaseTool
from argocd_mcp_server.exceptions import (
    ArgoCDOperationError,
    SyncOperationFailed,
    ApplicationNotFound,
    ValidationFailed,
    ArgoCDNotFoundError
)


class ApplicationManagerTools(BaseTool):
    """Tools for managing ArgoCD applications."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def list_applications(
            cluster_name: str = Field(..., min_length=1, description='Target Kubernetes cluster'),
            namespace: Optional[str] = Field(default=None, description='Filter by namespace (optional)'),
            project_filter: Optional[str] = Field(default=None, description='Filter by ArgoCD project (optional)'),
            status_filter: Optional[str] = Field(default=None, description='Filter by sync status: Synced, OutOfSync, Unknown'),
            limit: int = Field(default=50, description='Number of results per page'),
            offset: int = Field(default=0, description='Pagination offset'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """List all ArgoCD applications with pagination and filtering.
            
            Args:
                cluster_name: Target Kubernetes cluster
                namespace: Filter by namespace (optional)
                project_filter: Filter by ArgoCD project (optional)
                status_filter: Filter by sync status
                limit: Number of results per page
                offset: Pagination offset
            
            Returns:
                List of applications with metadata, health, and sync status
            """
            await ctx.info(
                f"Listing applications in cluster '{cluster_name}'",
                extra={'cluster_name': cluster_name, 'namespace': namespace}
            )
            
            try:
                result = await self.argocd_service.list_applications(
                    cluster_name=cluster_name,
                    namespace=namespace,
                    project_filter=project_filter,
                    status_filter=status_filter,
                    limit=limit,
                    offset=offset
                )
                
                await ctx.info(
                    f"Found {result['total']} applications",
                    extra={'total': result['total'], 'returned': len(result['applications'])}
                )
                
                return result
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to list applications: {error_msg}. "
                    "Please verify your ArgoCD authentication token and ensure the server is reachable. "
                    "If using the simulator, check if the server process is running."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        

        
        @mcp_instance.tool()
        async def get_application_details(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get detailed information about a specific ArgoCD application.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
            
            Returns:
                Complete application state with resources, sync history, health
            """
            await ctx.info(
                f"Getting details for application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                result = await self.argocd_service.get_application_details(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                await ctx.info(
                    f"Retrieved details for '{app_name}'",
                    extra={
                        'app_name': app_name,
                        'sync_status': result.get('sync_status'),
                        'health_status': result.get('health_status')
                    }
                )
                
                return result
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to get details for '{app_name}': {error_msg}. "
                    "Use 'list_applications' to verify the application exists and is accessible."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def create_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            project: str = Field(..., min_length=1, description='ArgoCD project'),
            repo_url: str = Field(..., min_length=1, description='Git repository URL'),
            path: str = Field(..., min_length=1, description='Path in repository'),
            destination_namespace: str = Field(..., min_length=1, description='Destination namespace'),
            target_revision: str = Field(default='HEAD', description='Git revision'),
            destination_server: str = Field(default='https://kubernetes.default.svc', description='Destination cluster'),
            auto_sync: bool = Field(default=False, description='Enable auto-sync'),
            prune: bool = Field(default=True, description='Enable pruning'),
            self_heal: bool = Field(default=True, description='Enable self-heal'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Create a new ArgoCD application.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                project: ArgoCD project
                repo_url: Git repository URL
                path: Path in repository
                target_revision: Git revision
                destination_server: Destination cluster
                destination_namespace: Destination namespace
                auto_sync: Enable auto-sync
                prune: Enable pruning
                self_heal: Enable self-heal
            
            Returns:
                Creation result
            """
            await ctx.info(
                f"Creating application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name, 'auto_sync': auto_sync}
            )
            
            try:
                result = await self.argocd_service.create_application(
                    cluster_name=cluster_name,
                    app_name=app_name,
                    project=project,
                    repo_url=repo_url,
                    path=path,
                    target_revision=target_revision,
                    destination_server=destination_server,
                    destination_namespace=destination_namespace,
                    auto_sync=auto_sync,
                    prune=prune,
                    self_heal=self_heal
                )
                
                await ctx.info(f"Successfully created application '{app_name}'")
                
                return result
            except Exception as e:
                error_msg = str(e)
                if "already exists" in error_msg.lower():
                    friendly_msg = (
                        f"Application '{app_name}' already exists. "
                        f"Use 'update_application' to modify its configuration, or "
                        f"'sync_application' to deploy changes."
                    )
                    await ctx.error(friendly_msg)
                    raise ArgoCDOperationError(friendly_msg)
                
                await ctx.error(f"Failed to create application: {error_msg}")
                raise ArgoCDOperationError(f"Failed to create application: {error_msg}")
        
        @mcp_instance.tool()
        async def update_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            target_revision: Optional[str] = Field(default=None, description='Git revision to update to'),
            auto_sync: Optional[bool] = Field(default=None, description='Enable/disable auto-sync'),
            prune: Optional[bool] = Field(default=None, description='Enable/disable pruning'),
            self_heal: Optional[bool] = Field(default=None, description='Enable/disable self-heal'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Update application configuration.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                target_revision: Git revision to update to
                auto_sync: Enable/disable auto-sync
                prune: Enable/disable pruning
                self_heal: Enable/disable self-heal
            
            Returns:
                Update result
            """
            await ctx.info(
                f"Updating application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                result = await self.argocd_service.update_application(
                    cluster_name=cluster_name,
                    app_name=app_name,
                    target_revision=target_revision,
                    auto_sync=auto_sync,
                    prune=prune,
                    self_heal=self_heal
                )
                
                await ctx.info(f"Successfully updated application '{app_name}'")
                
                return result
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to update application '{app_name}': {error_msg}. "
                    "Ensure the application exists using 'get_application_details' and that "
                    "the provided parameters are valid for the current configuration."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def delete_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            cascade: bool = Field(default=True, description='Delete related resources'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Delete an ArgoCD application.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                cascade: Delete related resources
            
            Returns:
                Deletion result
            """
            await ctx.warning(
                f"Deleting application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name, 'cascade': cascade}
            )
            
            try:
                result = await self.argocd_service.delete_application(
                    cluster_name=cluster_name,
                    app_name=app_name,
                    cascade=cascade
                )
                
                await ctx.info(f"Successfully deleted application '{app_name}'")
                
                return result
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to delete application '{app_name}': {error_msg}. "
                    "It may have already been deleted or you might lack permissions."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def validate_application_config(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Validate application configuration for errors.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
            
            Returns:
                Validation results with any errors or warnings
            """
            await ctx.info(
                f"Validating application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                # Use dedicated validate endpoint
                result = await self.argocd_service.validate_application_config(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                is_valid = result.get('valid', False)
                errors = result.get('details', [])  # Details often contain the errors
                if not is_valid and not errors:
                     # Fallback if no details but invalid
                     errors = [result.get('error', 'Unknown validation error')]

                if is_valid:
                    await ctx.info(f"Application '{app_name}' configuration is valid")
                else:
                    await ctx.warning(
                        f"Application '{app_name}' has validation errors",
                        extra={'errors': errors}
                    )
                
                return result
            except ApplicationNotFound:
                raise
            except ArgoCDNotFoundError:
                friendly_msg = (
                    f"Application '{app_name}' not found. Cannot validate configuration. "
                    "Please ensure the application is created first using 'create_application', "
                    "or check for typos in the application name."
                )
                await ctx.error(friendly_msg)
                raise ApplicationNotFound(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                     f"Validation failed for '{app_name}': {error_msg}. "
                     "Please check your Kubernetes manifests and ensure the repository URL is reachable."
                )
                await ctx.error(friendly_msg)
                raise ValidationFailed(friendly_msg)
        
        @mcp_instance.tool()
        async def get_application_events(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            limit: int = Field(default=50, description='Maximum number of events to return'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get recent events for an application (syncs, errors, etc).
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                limit: Maximum number of events to return
            
            Returns:
                List of recent events
            """
            await ctx.info(
                f"Getting events for application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                # Use dedicated events endpoint
                events = await self.argocd_service.get_application_events(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                if not events:
                    return {
                        'app_name': app_name,
                        'events': [],
                        'message': "No events found. The application might be new or not actively managed by ArgoCD recently."
                    }

                # Sort by lastTimestamp descending to show latest first
                # Note: API might not guarantee order.
                # Timestamps are strings, ISO8601.
                
                # Format events for readability
                formatted_events = []
                for event in events:
                    involved = event.get('involvedObject', {})
                    formatted_events.append({
                        'timestamp': event.get('lastTimestamp') or event.get('firstTimestamp'),
                        'type': event.get('type'),
                        'reason': event.get('reason'),
                        'message': event.get('message'),
                        'object': f"{involved.get('kind')}/{involved.get('name')}"
                    })
                
                # Sort locally to show latest first
                formatted_events.sort(key=lambda x: x['timestamp'] or '', reverse=True)
                
                # Apply limit
                limited_formatted_events = formatted_events[:limit]
                
                result = {
                    'app_name': app_name,
                    'events': limited_formatted_events
                }
                
                await ctx.info(
                    f"Retrieved {len(limited_formatted_events)} events for '{app_name}'",
                    extra={'event_count': len(limited_formatted_events)}
                )
                
                return result
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to get events for '{app_name}': {error_msg}. "
                    "If the application was just created, wait a few moments for events to generate."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
