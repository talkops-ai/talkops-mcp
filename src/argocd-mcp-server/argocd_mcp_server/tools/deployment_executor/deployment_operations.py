"""Deployment execution tools."""

from typing import Dict, Any, Optional
from pydantic import Field
from fastmcp import Context

from argocd_mcp_server.tools.base import BaseTool
from argocd_mcp_server.exceptions import (
    ArgoCDOperationError,
    SyncOperationFailed,
    ApplicationNotFound
)


class DeploymentExecutorTools(BaseTool):
    """Tools for executing and managing deployments."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def sync_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            revision: Optional[str] = Field(default=None, description='Specific Git revision to sync to'),
            dry_run: bool = Field(default=False, description='Simulate sync without applying changes'),
            prune: bool = Field(default=True, description='Delete resources not in Git'),
            auto_policy: str = Field(default='apply', description='Auto-sync policy: apply, create, sync_only'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Sync application to desired state.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                revision: Specific Git revision to sync to
                dry_run: Simulate sync without applying changes
                prune: Delete resources not in Git
                auto_policy: Auto-sync policy
            
            Returns:
                Sync operation result
            """
            await ctx.info(
                f"Syncing application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name, 'dry_run': dry_run}
            )
            
            try:
                result = await self.argocd_service.sync_application(
                    cluster_name=cluster_name,
                    app_name=app_name,
                    revision=revision,
                    dry_run=dry_run,
                    prune=prune,
                    auto_policy=auto_policy
                )
                
                await ctx.info(f"Sync initiated for '{app_name}'")
                
                # Create human-readable summary
                details = result.get('details', {})
                is_dry_run = details.get('dry_run', False)
                action = "Dry-run sync" if is_dry_run else "Sync operation"
                status = result.get('status')
                message = result.get('message')
                
                summary = f"{action} for '{app_name}' resulted in status '{status}'. {message}"
                
                # Return summary at top level for agent visibility
                return {
                    "summary": summary,
                    **result
                }
            except SyncOperationFailed:
                raise
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to sync application '{app_name}': {error_msg}. "
                    "Try running 'get_application_diff' to check for configuration issues, "
                    "or 'get_application_logs' if the sync operation started but failed."
                )
                await ctx.error(friendly_msg)
                raise SyncOperationFailed(friendly_msg)
        
        @mcp_instance.tool()
        async def get_application_diff(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            target_revision: Optional[str] = Field(default=None, description='Target Git revision'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Show what changes will happen before syncing.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                target_revision: Target Git revision
            
            Returns:
                Diff showing what will change
            """
            await ctx.info(
                f"Getting diff for application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                result = await self.argocd_service.get_application_diff(
                    cluster_name=cluster_name,
                    app_name=app_name,
                    revision=target_revision
                )
                
                changes_count = len(result.get('diffs', []))
                await ctx.info(
                    f"Found {changes_count} changes for '{app_name}'",
                    extra={'changes_detected': result.get('changes_detected')}
                )
                
                return result
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to get diff for '{app_name}': {error_msg}. "
                    "Ensure the application exists and the Git repository is accessible."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def get_application_logs(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            tail_lines: int = Field(default=50, description='Number of recent log lines to retrieve per pod (max 200)'),
            follow: bool = Field(default=False, description='Stream logs'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get logs from application pods.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                tail_lines: Number of recent log lines to retrieve per pod (default: 50, max: 200)
                follow: Stream logs
            
            Returns:
                Application logs summary with recent entries
            """
            await ctx.info(
                f"Getting logs for application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            # Limit tail_lines to a reasonable maximum
            tail_lines = min(tail_lines, 200)
            
            try:
                # Get application resource tree to find actual pods
                try:
                    tree = await self.argocd_service.get_application_resource_tree(
                        cluster_name=cluster_name,
                        app_name=app_name
                    )
                    nodes = tree.get('nodes', [])
                    pod_resources = [n for n in nodes if n.get('kind') == 'Pod']
                except Exception:
                    # Fallback if tree fails
                    app_details = await self.argocd_service.get_application_details(
                        cluster_name=cluster_name,
                        app_name=app_name
                    )
                    resources = app_details.get('resources', [])
                    pod_resources = [r for r in resources if r.get('kind') == 'Pod']
                
                logs_summary = []
                total_lines_collected = 0
                
                for pod in pod_resources[:5]:  # Limit to first 5 pods
                    pod_name = pod.get('name')
                    namespace = pod.get('namespace')
                    
                    if pod_name:
                        try:
                            # Get logs from ArgoCD API
                            pod_logs_raw = await self.argocd_service.get_application_logs(
                                cluster_name=cluster_name,
                                app_name=app_name,
                                pod_name=pod_name,
                                namespace=namespace,
                                tail=tail_lines,
                                follow=follow
                            )
                            
                            # Parse and limit log output
                            # The logs might be a string or dict, handle both
                            if isinstance(pod_logs_raw, str):
                                log_lines = pod_logs_raw.strip().split('\n') if pod_logs_raw else []
                            else:
                                # If it's a dict or other format, convert to string
                                log_lines = str(pod_logs_raw).strip().split('\n')
                            
                            # Take only the requested number of tail lines
                            log_lines = log_lines[-tail_lines:] if len(log_lines) > tail_lines else log_lines
                            total_lines_collected += len(log_lines)
                            
                            # Create a concise summary
                            pod_summary = {
                                'pod_name': pod_name,
                                'namespace': namespace,
                                'line_count': len(log_lines),
                                'recent_logs': log_lines[:20] if len(log_lines) > 20 else log_lines,  # Show only first 20 lines in summary
                                'has_more': len(log_lines) > 20
                            }
                            
                            # Add error indicators if present in logs
                            error_keywords = ['error', 'fatal', 'exception', 'failed', 'panic']
                            error_lines = [line for line in log_lines if any(kw in line.lower() for kw in error_keywords)]
                            if error_lines:
                                pod_summary['error_count'] = len(error_lines)
                                pod_summary['sample_errors'] = error_lines[:5]  # Show up to 5 error samples
                            
                            logs_summary.append(pod_summary)
                            
                        except Exception as pod_error:
                            logs_summary.append({
                                'pod_name': pod_name,
                                'namespace': namespace,
                                'error': str(pod_error)
                            })
                
                # Create human-readable summary
                pod_count = len(pod_resources)
                logs_retrieved = len([l for l in logs_summary if 'error' not in l])
                
                summary_text = (
                    f"Retrieved logs from {logs_retrieved}/{pod_count} pods for application '{app_name}'. "
                    f"Total {total_lines_collected} log lines collected (showing recent {tail_lines} lines per pod). "
                )
                
                # Check for errors across all pods
                pods_with_errors = [l for l in logs_summary if l.get('error_count', 0) > 0]
                if pods_with_errors:
                    summary_text += f"⚠️  {len(pods_with_errors)} pod(s) have error messages in logs."
                        
                result = {
                    'summary': summary_text,
                    'app_name': app_name,
                    'total_pods': pod_count,
                    'pods_checked': len(logs_summary),
                    'tail_lines_per_pod': tail_lines,
                    'total_lines_collected': total_lines_collected,
                    'pod_logs': logs_summary
                }
                
                await ctx.info(f"Retrieved logs for {logs_retrieved} pods in '{app_name}' ({total_lines_collected} lines total)")
                
                return result
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to get logs for '{app_name}': {error_msg}. "
                    "Check if pods are running or in a CrashLoopBackOff state using 'get_application_details'."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def get_sync_status(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get current sync status and operation progress.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
            
            Returns:
                Current sync status
            """
            await ctx.info(
                f"Getting sync status for '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                result = await self.argocd_service.get_sync_status(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                await ctx.info(
                    f"Application '{app_name}' status retrieved",
                    extra={'sync_status': result.get('sync', {}).get('status', 'Unknown')}
                )
                
                return result
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to get sync status for '{app_name}': {error_msg}. "
                    "Verify the application exists."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def rollback_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            steps: int = Field(default=1, description='How many revisions back to rollback'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Rollback application to previous sync.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                steps: How many revisions back to rollback
            
            Returns:
                Rollback result
            """
            await ctx.warning(
                f"Rolling back application '{app_name}' by {steps} revision(s)",
                extra={'cluster_name': cluster_name, 'app_name': app_name, 'steps': steps}
            )
            
            try:
                # Get sync history to find target revision
                app_details = await self.argocd_service.get_application_details(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                sync_history = app_details.get('sync_history', [])
                if len(sync_history) < steps + 1:
                    raise ArgoCDOperationError(
                        f"Cannot rollback {steps} steps. Only {len(sync_history)} revisions available"
                    )
                
                target_revision = sync_history[steps].get('revision')
                
                # Use rollback_to_revision service method
                result = await self.argocd_service.rollback_to_revision(
                    cluster_name=cluster_name,
                    app_name=app_name,
                    revision=target_revision
                )
                
                await ctx.info(f"Rolled back '{app_name}' to revision {target_revision}")
                
                return result
            except SyncOperationFailed:
                raise
            except ApplicationNotFound:
                raise
            except ArgoCDOperationError:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to rollback '{app_name}': {error_msg}. "
                    f"Ensure you are rolling back to a valid history index. Use 'get_application_details' to see history."
                )
                await ctx.error(friendly_msg)
                raise SyncOperationFailed(friendly_msg)
        
        @mcp_instance.tool()
        async def rollback_to_revision(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            revision: str = Field(..., min_length=1, description='Git revision'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Rollback to specific Git revision.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                revision: Git revision
            
            Returns:
                Rollback result
            """
            await ctx.warning(
                f"Rolling back application '{app_name}' to revision {revision}",
                extra={'cluster_name': cluster_name, 'app_name': app_name, 'revision': revision}
            )
            
            try:
                result = await self.argocd_service.rollback_to_revision(
                    cluster_name=cluster_name,
                    app_name=app_name,
                    revision=revision
                )
                
                await ctx.info(f"Rolled back '{app_name}' to revision {revision}")
                
                return result
            except SyncOperationFailed:
                raise
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to rollback '{app_name}' to revision '{revision}': {error_msg}. "
                    "Verify the revision hash is correct and exists in the Git repository."
                )
                await ctx.error(friendly_msg)
                raise SyncOperationFailed(friendly_msg)
        
        @mcp_instance.tool()
        async def prune_resources(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            dry_run: bool = Field(default=True, description='Preview pruning without deletion'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Remove resources not in Git (safe cleanup).
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                dry_run: Preview pruning without deletion
            
            Returns:
                Prune result
            """
            await ctx.warning(
                f"Pruning resources for '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name, 'dry_run': dry_run}
            )
            
            try:
                if dry_run:
                     result = await self.argocd_service.sync_application(
                        cluster_name=cluster_name,
                        app_name=app_name,
                        dry_run=True,
                        prune=True,
                        auto_policy='apply'
                     )
                else:
                     result = await self.argocd_service.prune_resources(
                        cluster_name=cluster_name,
                        app_name=app_name,
                        cascade=True
                     )
                
                await ctx.info(f"Prune operation completed for '{app_name}'")
                
                return result
            except SyncOperationFailed:
                raise
            except ApplicationNotFound:
                raise
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to prune resources for '{app_name}': {error_msg}. "
                    "Check the sync status; resources might already be Pruned or missing."
                )
                await ctx.error(friendly_msg)
                raise SyncOperationFailed(friendly_msg)
        
        @mcp_instance.tool()
        async def hard_refresh(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Hard refresh application state (bypass cache).
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
            
            Returns:
                Refresh result
            """
            await ctx.info(
                f"Hard refreshing application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                # Use dedicated hard refresh
                result = await self.argocd_service.hard_refresh(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                await ctx.info(f"Hard refresh completed for '{app_name}'")
                
                return {
                    'app_name': app_name,
                    'refreshed': True,
                    'sync_status': result.get('sync_status'),
                    'health_status': result.get('health_status')
                }
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to hard refresh '{app_name}': {error_msg}. "
                    "The application might be unreachable or deleted."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def soft_refresh(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Soft refresh application state (use cache).
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
            
            Returns:
                Refresh result
            """
            await ctx.info(
                f"Soft refreshing application '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name}
            )
            
            try:
                result = await self.argocd_service.soft_refresh(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                await ctx.info(f"Soft refresh completed for '{app_name}'")
                
                return {
                    'app_name': app_name,
                    'refreshed': True,
                    'sync_status': result.get('sync_status'),
                    'health_status': result.get('health_status')
                }
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to soft refresh '{app_name}': {error_msg}. "
                    "The application might be unreachable or deleted."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool()
        async def cancel_deployment(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            operation_id: str = Field(..., min_length=1, description='Operation ID to cancel'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Cancel ongoing sync operation.
            
            Args:
                cluster_name: Target cluster
                app_name: Application name
                operation_id: Operation ID to cancel
            
            Returns:
                Cancellation result
            """
            await ctx.warning(
                f"Cancelling deployment for '{app_name}'",
                extra={'cluster_name': cluster_name, 'app_name': app_name, 'operation_id': operation_id}
            )
            
            try:
                # Use dedicated cancel endpoint
                result = await self.argocd_service.cancel_deployment(
                    cluster_name=cluster_name,
                    app_name=app_name
                )
                
                # Check for "operation_id" usage? The service cancel_deployment doesn't take operation_id, 
                # but tool has it. The API DELETE .../operation cancels *current* operation.
                # So we ignore/log usage of operation_id as legacy or decorative if API doesn't use it.
                if operation_id:
                     pass # or log it
                
                result['operation_id'] = operation_id 
                result['cancelled'] = True
                
                await ctx.info(f"Cancelled deployment for '{app_name}'")
                
                return result
            except Exception as e:
                error_msg = str(e)
                friendly_msg = (
                    f"Failed to cancel deployment for '{app_name}': {error_msg}. "
                    "There might be no active operation to cancel."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
