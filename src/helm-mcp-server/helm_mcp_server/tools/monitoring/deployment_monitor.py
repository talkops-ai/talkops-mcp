"""Helm deployment monitoring and status tools."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastmcp import Context
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.tools.base import BaseTool


class MonitoringTools(BaseTool):
    """Tools for monitoring Helm deployments and release status."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def helm_monitor_deployment(
            release_name: str = Field(..., description='Release name to monitor'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            max_wait_seconds: int = Field(default=60, description='Maximum time to wait in seconds'),
            check_interval: int = Field(default=5, description='Interval between checks in seconds'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Monitor deployment health asynchronously.
            
            Polls pod status until ready or timeout.
            
            Args:
                release_name: Release name to monitor
                namespace: Kubernetes namespace
                max_wait_seconds: Maximum time to wait for deployment to be ready
                check_interval: Interval between checks in seconds
            
            Returns:
                Monitoring result with deployment status
            
            Raises:
                HelmOperationError: If monitoring fails or timeout
            """
            await ctx.info(
                f"Starting deployment monitoring for '{release_name}'",
                extra={
                    'release_name': release_name,
                    'namespace': namespace,
                    'max_wait_seconds': max_wait_seconds
                }
            )
            
            await ctx.debug( f'Checking pod status every {check_interval} seconds')
            
            try:
                result = await self.helm_service.monitor_deployment_health(
                    release_name=release_name,
                    namespace=namespace,
                    max_wait_seconds=max_wait_seconds,
                    check_interval=check_interval,
                )
                
                await ctx.info(
                    f"Deployment '{release_name}' is ready",
                    extra={
                        'release_name': release_name,
                        'pod_count': result.get('pod_count', 0),
                        'ready_pods': result.get('ready_pods', 0),
                        'duration_seconds': result.get('duration_seconds', 0)
                    }
                )
                
                return result
            
            except HelmOperationError as e:
                if 'not ready after' in str(e):
                    await ctx.warning(
                        f"Deployment '{release_name}' did not become ready within timeout",
                        extra={
                            'release_name': release_name,
                            'max_wait_seconds': max_wait_seconds,
                            'error': str(e)
                        }
                    )
                else:
                    await ctx.error(
                        f"Monitoring failed: {str(e)}",
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
        
        @mcp_instance.tool()
        async def helm_get_release_status(
            release_name: str = Field(..., description='Release name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get current status of a Helm release.
            
            Args:
                release_name: Release name
                namespace: Kubernetes namespace
            
            Returns:
                Release status information
            
            Raises:
                HelmOperationError: If status retrieval fails
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

