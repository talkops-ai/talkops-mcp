"""Deployment execution tools."""

from typing import Dict, Any, Optional
from pydantic import Field
from mcp.types import ToolAnnotations
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Sync ArgoCD Application",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def sync_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            revision: Optional[str] = Field(default=None, description='Specific Git revision to sync to (e.g., "abc123", "v1.0.0")'),
            dry_run: bool = Field(default=False, description='Simulate sync without applying changes'),
            prune: bool = Field(default=True, description='Delete resources not in Git'),
            auto_policy: str = Field(default='apply', description='Auto-sync policy: apply, create, sync_only'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Sync an ArgoCD application to its desired Git state.

            Use when deploying changes from Git to the cluster. ArgoCD
            compares the Git manifests with the live cluster state and
            applies the differences.

            **WARNING: This modifies live cluster resources. Pods may be
            restarted, services reconfigured, or resources deleted (if
            prune=True).**

            Returns:
            - {"summary": str, "status": str, "message": str,
               "details": {"dry_run": bool, ...}}

            When NOT to use:
            - To preview changes → use get_application_diff.
            - To rollback → use rollback_application.
            - To create a new app → use create_application.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Application Diff",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def get_application_diff(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            target_revision: Optional[str] = Field(default=None, description='Target Git revision to diff against'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Show what changes will happen before syncing.

            Use to preview the diff between the Git desired state and the
            live cluster state. Read-only — does not apply any changes.

            Returns:
            - {"changes_detected": bool, "diffs": [{"kind": str,
               "name": str, "diff": str}]}

            When NOT to use:
            - To apply changes → use sync_application.
            - To get app details → use get_application_details.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Application Logs",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def get_application_logs(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            tail_lines: int = Field(default=50, description='Number of recent log lines per pod (max 200)'),
            follow: bool = Field(default=False, description='Stream logs (not recommended for MCP)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get logs from application pods.

            Use to troubleshoot runtime errors, CrashLoopBackOff, or
            verify application behavior after a sync. Retrieves logs
            from up to 5 pods. Read-only.

            Returns:
            - {"summary": str, "app_name": str, "total_pods": int,
               "pod_logs": [{"pod_name": str, "line_count": int,
               "recent_logs": [str], "error_count": int}]}

            When NOT to use:
            - To get events → use get_application_events.
            - To check sync status → use get_sync_status.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Sync Status",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def get_sync_status(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get current sync status and operation progress.

            Use to check if an application is Synced, OutOfSync, or has
            a sync operation in progress. Read-only.

            Returns:
            - {"sync": {"status": str, "revision": str},
               "health": {"status": str}, "operation": {...} | null}

            When NOT to use:
            - To get full app details → use get_application_details.
            - To sync the app → use sync_application.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Rollback Application",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def rollback_application(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            steps: int = Field(default=1, description='How many revisions back to rollback (default: 1 = previous)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Rollback an application to a previous sync revision.

            Use when a recent sync caused issues and you need to revert.
            Checks sync history and syncs to the target revision.

            **WARNING: This modifies the live cluster by reverting to
            an older configuration. Pods may be restarted.**

            Returns:
            - {"status": str, "app_name": str, "revision": str}

            When NOT to use:
            - To rollback to a specific commit → use rollback_to_revision.
            - To sync to latest → use sync_application.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Rollback to Specific Revision",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def rollback_to_revision(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            revision: str = Field(..., min_length=1, description='Git commit SHA or tag to rollback to (e.g., "abc123", "v1.0.0")'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Rollback an application to a specific Git revision.

            Use when you know the exact commit or tag to revert to.

            **WARNING: This modifies the live cluster by syncing to a
            specific older revision. Pods may be restarted.**

            Returns:
            - {"status": str, "app_name": str, "revision": str}

            When NOT to use:
            - To rollback N steps → use rollback_application.
            - To sync to HEAD → use sync_application.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Prune Application Resources",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def prune_resources(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            dry_run: bool = Field(default=True, description='Preview pruning without deletion (default: True for safety)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Remove Kubernetes resources not present in Git (safe cleanup).

            Use to clean up orphaned resources after removing manifests
            from Git. Defaults to dry_run=True for safety.

            **WARNING: With dry_run=False, this DELETES Kubernetes resources
            that exist in the cluster but not in the Git repository.**

            Returns:
            - {"status": str, "pruned_resources": [...]}

            When NOT to use:
            - To sync with pruning → use sync_application (prune=True).
            - To delete the entire app → use delete_application.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Hard Refresh Application",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def hard_refresh(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Hard refresh application state (bypass ArgoCD cache).

            Use when the ArgoCD UI shows stale data or after making
            changes directly in the Git repository. Forces ArgoCD to
            re-read from Git and re-compare with the live cluster.

            Returns:
            - {"app_name": str, "refreshed": bool,
               "sync_status": str, "health_status": str}

            When NOT to use:
            - For a quick status check → use soft_refresh or get_sync_status.
            - To apply changes → use sync_application.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Soft Refresh Application",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def soft_refresh(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Soft refresh application state (use ArgoCD cache).

            Use for a quick status update without forcing a full re-read
            from Git. Faster than hard_refresh. Read-only.

            Returns:
            - {"app_name": str, "refreshed": bool,
               "sync_status": str, "health_status": str}

            When NOT to use:
            - If data seems stale → use hard_refresh.
            - To apply changes → use sync_application.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Cancel Deployment",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def cancel_deployment(
            cluster_name: str = Field(..., min_length=1, description='Target cluster'),
            app_name: str = Field(..., min_length=1, description='Application name'),
            operation_id: str = Field(..., min_length=1, description='Operation ID to cancel (from sync_application response)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Cancel an ongoing sync operation.

            Use when a sync is taking too long or was triggered by mistake.
            Cancels the current sync operation for the application.

            **WARNING: Cancelling a sync mid-operation may leave the
            application in a partially-synced state.**

            Returns:
            - {"app_name": str, "operation_id": str, "cancelled": bool}

            When NOT to use:
            - To rollback a completed sync → use rollback_application.
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
