"""Helm deployment monitoring and status tools."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from mcp.types import ToolAnnotations
from fastmcp import Context
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.tools.base import BaseTool


class MonitoringTools(BaseTool):
    """Tools for monitoring Helm deployments and release status."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Monitor Helm Deployment Health",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def helm_monitor_deployment(
            release_name: str = Field(..., description='Release name to monitor (e.g., "my-postgres")'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            max_wait_seconds: int = Field(default=60, description='Maximum time to wait in seconds (default: 60)'),
            check_interval: int = Field(default=5, description='Interval between checks in seconds (default: 5)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Monitor deployment health after a Helm install or upgrade.

            Use after helm_install_chart or helm_upgrade_release to verify
            the deployment is healthy. Performs multi-layer health checking:
            - Helm release status (catches hook/manifest failures)
            - Deployment/StatefulSet rollout status (replica counts)
            - Pod container diagnostics (CrashLoopBackOff, ImagePullBackOff)

            Read-only — only observes cluster state.

            Returns:
            - {"status": "ready"|"failed"|"timeout",
               "duration_seconds": int, "deployments": [...],
               "pod_summary": {...}, "issues": [{...}]}

            When NOT to use:
            - To get current release status → use helm_get_release_status.
            - To install a release → use helm_install_chart.
            """
            await ctx.info(
                f"Starting deployment monitoring for '{release_name}'",
                extra={
                    'release_name': release_name,
                    'namespace': namespace,
                    'max_wait_seconds': max_wait_seconds
                }
            )
            
            await ctx.debug(f'Checking deployment health every {check_interval} seconds')
            
            try:
                result = await self.helm_service.monitor_deployment_health(
                    release_name=release_name,
                    namespace=namespace,
                    max_wait_seconds=max_wait_seconds,
                    check_interval=check_interval,
                )
                
                status = result.get('status', 'unknown')
                issues = result.get('issues', [])
                pod_summary = result.get('pod_summary', {})
                deployments = result.get('deployments', [])
                
                if status == 'ready':
                    await ctx.info(
                        f"Deployment '{release_name}' is ready",
                        extra={
                            'release_name': release_name,
                            'duration_seconds': result.get('duration_seconds', 0),
                            'pod_summary': pod_summary,
                            'deployment_count': len(deployments),
                        }
                    )
                
                elif status == 'failed':
                    error_issues = [i for i in issues if i.get('severity') == 'error']
                    await ctx.error(
                        f"Deployment '{release_name}' has failed",
                        extra={
                            'release_name': release_name,
                            'duration_seconds': result.get('duration_seconds', 0),
                            'issue_count': len(error_issues),
                            'issues': error_issues,
                        }
                    )
                
                elif status == 'timeout':
                    await ctx.warning(
                        f"Deployment '{release_name}' did not become ready within {max_wait_seconds}s",
                        extra={
                            'release_name': release_name,
                            'max_wait_seconds': max_wait_seconds,
                            'pod_summary': pod_summary,
                            'issues': issues,
                        }
                    )
                
                return result
            
            except HelmOperationError as e:
                await ctx.error(
                    f"Monitoring infrastructure error: {str(e)}",
                    extra={
                        'release_name': release_name,
                        'error': str(e)
                    }
                )
                raise
            except Exception as e:
                await ctx.error(
                    f"Deployment monitoring failed: {str(e)}",
                    extra={
                        'release_name': release_name,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Deployment monitoring failed: {str(e)}')
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Helm Release Status",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def helm_get_release_status(
            release_name: str = Field(..., description='Release name (e.g., "my-postgres")'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get current status of a Helm release.

            Use to check if a release is deployed, failed, or pending.
            Read-only — only queries cluster state.

            Returns:
            - {"release_info": {"status": str, "revision": int,
               "chart": str, "app_version": str, ...}}

            When NOT to use:
            - To monitor deployment health over time → use helm_monitor_deployment.
            - To list all releases → use kubernetes_get_helm_releases.
            """
            await ctx.info(
                f"Fetching status for release '{release_name}'",
                extra={
                    'release_name': release_name,
                    'namespace': namespace
                }
            )
            
            await ctx.debug( 'Querying Helm for release status')
            
            try:
                result = await self.helm_service.get_release_status(
                    release_name=release_name,
                    namespace=namespace,
                )
                
                release_info = result.get('release_info', {})
                status = release_info.get('status', 'unknown')
                
                await ctx.info(
                    f"Retrieved status for release '{release_name}': {status}",
                    extra={
                        'release_name': release_name,
                        'namespace': namespace,
                        'status': status
                    }
                )
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Failed to get release status: {str(e)}",
                    extra={
                        'release_name': release_name,
                        'namespace': namespace,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Failed to get release status: {str(e)}')
