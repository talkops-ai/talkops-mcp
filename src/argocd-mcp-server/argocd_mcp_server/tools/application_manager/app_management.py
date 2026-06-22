"""Application management tools."""

from typing import Dict, Any, Optional
from pydantic import Field
from mcp.types import ToolAnnotations
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List ArgoCD Applications",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def list_applications(
            cluster_name: str = Field(..., min_length=1, description='Target Kubernetes cluster'),
            namespace: Optional[str] = Field(default=None, description='Filter by namespace (optional)'),
            project_filter: Optional[str] = Field(default=None, description='Filter by ArgoCD project (optional)'),
            status_filter: Optional[str] = Field(default=None, description='Filter by sync status: Synced, OutOfSync, Unknown'),
            limit: int = Field(default=50, description='Number of results per page'),
            offset: int = Field(default=0, description='Pagination offset'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List all ArgoCD applications with pagination and filtering.

            Use to discover deployed applications, check their sync/health
            status, or filter by namespace, project, or status. Read-only.

            Returns:
            - {"total": int, "applications": [{"name": str,
               "sync_status": str, "health_status": str, ...}]}

            When NOT to use:
            - To get details of a specific app → use get_application_details.
            - To check sync status → use get_sync_status.
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
                error_lower = error_msg.lower()
                
                # Only suggest auth/connectivity troubleshooting when the error
                # actually indicates an authentication or connection problem.
                if any(kw in error_lower for kw in (
                    "unauthorized", "401", "403", "forbidden",
                    "connection", "timeout", "unreachable", "refused",
                )):
                    friendly_msg = (
                        f"Failed to list applications: {error_msg}. "
                        "Please verify your ArgoCD authentication token and ensure the server is reachable. "
                        "If using the simulator, check if the server process is running."
                    )
                else:
                    friendly_msg = f"Failed to list applications: {error_msg}"
                    
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        

        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get ArgoCD Application Details",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def get_application_details(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get detailed information about a specific ArgoCD application.

            Use to inspect an application's full state including resources,
            sync history, health status, and configuration. Read-only.

            Returns:
            - {"name": str, "sync_status": str, "health_status": str,
               "resources": [...], "sync_history": [...], ...}

            When NOT to use:
            - To list all apps → use list_applications.
            - To check sync status only → use get_sync_status.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create ArgoCD Application",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def create_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            project: str = Field(..., min_length=1, description='ArgoCD project (e.g., "default", "production")'),
            repo_url: str = Field(..., min_length=1, description='Git repository URL (e.g., "https://github.com/org/repo.git")'),
            path: str = Field(..., min_length=1, description='Path to manifests in repository (e.g., "k8s/", "helm/my-app")'),
            destination_namespace: str = Field(..., min_length=1, description='Target Kubernetes namespace (e.g., "production")'),
            target_revision: str = Field(default='HEAD', description='Git branch, tag, or commit SHA (e.g., "main", "v1.0.0")'),
            destination_server: str = Field(default='https://kubernetes.default.svc', description='Destination cluster API URL'),
            auto_sync: bool = Field(default=False, description='Enable auto-sync (ArgoCD automatically applies changes from Git)'),
            prune: bool = Field(default=True, description='Enable pruning (delete resources removed from Git)'),
            self_heal: bool = Field(default=True, description='Enable self-heal (revert manual cluster changes to match Git)'),
            create_namespace: bool = Field(default=False, description='Create destination namespace if it does not exist'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Create a new ArgoCD application for GitOps deployment.

            Use when setting up a new application to be managed by ArgoCD.
            The Git repository must already be registered (use
            onboard_repository_https or onboard_repository_ssh first).

            **WARNING: This creates an ArgoCD Application resource. If
            auto_sync is enabled, resources will be deployed immediately.**

            Returns:
            - {"status": str, "app_name": str, "namespace": str, ...}

            When NOT to use:
            - To update an existing app → use update_application.
            - To sync an existing app → use sync_application.

            Common errors:
            - Application already exists: Use update_application instead.
            - Repository not found: Register with onboard_repository_https first.
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
                    self_heal=self_heal,
                    create_namespace=create_namespace
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Update ArgoCD Application",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def update_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            target_revision: Optional[str] = Field(default=None, description='Git revision to update to (e.g., "main", "v2.0.0")'),
            auto_sync: Optional[bool] = Field(default=None, description='Enable/disable auto-sync'),
            prune: Optional[bool] = Field(default=None, description='Enable/disable pruning'),
            self_heal: Optional[bool] = Field(default=None, description='Enable/disable self-heal'),
            create_namespace: Optional[bool] = Field(default=None, description='Enable/disable namespace creation'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Update an existing ArgoCD application configuration.

            Use when changing sync policies, target revision, or other
            settings on an already-created application.

            **WARNING: Changes to auto_sync or target_revision may trigger
            an immediate sync, deploying new resources to the cluster.**

            Returns:
            - {"status": str, "app_name": str, "updated_fields": [...]}

            When NOT to use:
            - To create a new app → use create_application.
            - To sync an app → use sync_application.
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
                    self_heal=self_heal,
                    create_namespace=create_namespace
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete ArgoCD Application",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def delete_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            cascade: bool = Field(default=True, description='Delete related Kubernetes resources (Deployments, Services, etc.)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Delete an ArgoCD application.

            Use when permanently removing an application from ArgoCD management.

            **WARNING: DESTRUCTIVE — With cascade=True (default), this
            deletes ALL Kubernetes resources managed by the application
            (Deployments, Services, ConfigMaps, etc.). This cannot be undone.**

            Returns:
            - {"status": str, "app_name": str, "cascade": bool}

            When NOT to use:
            - To rollback → use rollback_application.
            - To stop syncing without deleting → use update_application (disable auto_sync).
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate Application Configuration",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def validate_application_config(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Validate an ArgoCD application's configuration for errors.

            Use before syncing to catch manifest errors, missing resources,
            or misconfigured sources. Read-only — does not modify state.

            Returns:
            - {"valid": bool, "details": [str], "error": str | null}

            When NOT to use:
            - To sync the app → use sync_application.
            - To view app state → use get_application_details.
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
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            limit: int = Field(default=50, description='Maximum number of events to return'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get recent events for an ArgoCD application (syncs, errors, etc).

            Use to troubleshoot sync failures, view deployment history, or
            check for warnings. Events are sorted by timestamp (latest first).
            Read-only.

            Returns:
            - {"app_name": str, "events": [{"timestamp": str, "type": str,
               "reason": str, "message": str, "object": str}]}

            When NOT to use:
            - To get app logs → use get_application_logs.
            - To get sync status → use get_sync_status.
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
