"""Kubernetes cluster inspection and operations tools."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastmcp import Context
from helm_mcp_server.exceptions import KubernetesOperationError
from helm_mcp_server.tools.base import BaseTool


class KubernetesTools(BaseTool):
    """Tools for Kubernetes cluster inspection and operations."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def kubernetes_get_cluster_info(
            ctx: Context
        ) -> Dict[str, Any]:
            """Get cluster information.
            
            Returns:
                Cluster information
            
            Raises:
                KubernetesOperationError: If getting cluster info fails
            """
            await ctx.info( 'Fetching Kubernetes cluster information')
            
            await ctx.debug( 'Connecting to Kubernetes API')
            
            try:
                info = await self.k8s_service.get_cluster_info()
                
                await ctx.info(
                    f"Retrieved cluster info: {info['node_count']} nodes, {info['namespace_count']} namespaces",
                    extra={
                        'kubernetes_version': info.get('kubernetes_version'),
                        'node_count': info.get('node_count', 0),
                        'namespace_count': info.get('namespace_count', 0)
                    }
                )
                
                return info
            
            except Exception as e:
                await ctx.error(
                    f"Failed to get cluster info: {str(e)}",
                    extra={'error': str(e)}
                )
                raise KubernetesOperationError(f'Failed to get cluster info: {str(e)}')
        
        @mcp_instance.tool()
        async def kubernetes_list_namespaces(
            ctx: Context
        ) -> List[str]:
            """List all Kubernetes namespaces.
            
            Returns:
                List of namespace names
            
            Raises:
                KubernetesOperationError: If listing fails
            """
            await ctx.info( 'Listing Kubernetes namespaces')
            
            await ctx.debug( 'Querying Kubernetes API for namespaces')
            
            try:
                namespaces = await self.k8s_service.list_namespaces()
                
                await ctx.info(
                    f"Found {len(namespaces)} namespaces",
                    extra={
                        'namespace_count': len(namespaces),
                        'namespaces': namespaces
                    }
                )
                
                return namespaces
            
            except Exception as e:
                await ctx.error(
                    f"Failed to list namespaces: {str(e)}",
                    extra={'error': str(e)}
                )
                raise KubernetesOperationError(f'Failed to list namespaces: {str(e)}')
        
        @mcp_instance.tool()
        async def kubernetes_get_helm_releases(
            ctx: Context,
            namespace: Optional[str] = Field(default=None, description='Optional namespace filter (if None, lists all namespaces)')
        ) -> List[Dict[str, Any]]:
            """List all Helm releases in cluster.
            
            Args:
                namespace: Optional namespace filter (if None, lists all namespaces)
            
            Returns:
                List of Helm release information
            
            Raises:
                KubernetesOperationError: If listing fails
            """
            if namespace:
                await ctx.info( f"Listing Helm releases in namespace '{namespace}'")
            else:
                await ctx.info( 'Listing Helm releases across all namespaces')
            
            await ctx.debug( 'Querying Helm for releases')
            
            try:
                releases = await self.k8s_service.get_helm_releases(namespace=namespace)
                
                await ctx.info(
                    f"Found {len(releases)} Helm release(s)",
                    extra={
                        'release_count': len(releases),
                        'namespace': namespace,
                        'releases': [r.get('name', 'unknown') for r in releases]
                    }
                )
                
                if len(releases) == 0:
                    await ctx.debug( 'No Helm releases found')
                
                return releases
            
            except Exception as e:
                await ctx.error(
                    f"Failed to get Helm releases: {str(e)}",
                    extra={
                        'namespace': namespace,
                        'error': str(e)
                    }
                )
                raise KubernetesOperationError(f'Failed to get Helm releases: {str(e)}')
        
        @mcp_instance.tool()
        async def kubernetes_check_prerequisites(
            ctx: Context,
            required_api_version: Optional[str] = Field(default=None, description='Required Kubernetes API version (e.g., v1.28.0)'),
            required_resources: Optional[List[str]] = Field(default=None, description='List of required resource types (e.g., [Deployment, Service])')
        ) -> Dict[str, Any]:
            """Check if cluster meets installation prerequisites.
            
            Args:
                required_api_version: Required Kubernetes API version (e.g., 'v1.28.0')
                required_resources: List of required resource types (e.g., ['Deployment', 'Service'])
            
            Returns:
                Prerequisites check result with status
            
            Raises:
                KubernetesOperationError: If check fails
            """
            await ctx.info(
                'Checking cluster prerequisites',
                extra={
                    'required_api_version': required_api_version,
                    'required_resources': required_resources
                }
            )
            
            await ctx.debug( 'Validating cluster version and resource availability')
            
            try:
                result = await self.k8s_service.check_prerequisites(
                    required_api_version=required_api_version,
                    required_resources=required_resources,
                )
                
                all_met = result.get('all_prerequisites_met', False)
                
                if all_met:
                    await ctx.info(
                        'All prerequisites met',
                        extra={
                            'cluster_version': result.get('cluster_version'),
                            'all_prerequisites_met': True
                        }
                    )
                else:
                    missing_resources = result.get('resource_check', {}).get('missing', [])
                    api_check = result.get('api_version_check', {})
                    
                    if not api_check.get('meets_requirement', True):
                        await ctx.warning(
                            f"API version requirement not met: requires {api_check.get('required')}, cluster has {api_check.get('current')}",
                            extra={'api_version_check': api_check}
                        )
                    
                    if missing_resources:
                        await ctx.warning(
                            f"Missing required resources: {', '.join(missing_resources)}",
                            extra={'missing_resources': missing_resources}
                        )
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Prerequisites check failed: {str(e)}",
                    extra={'error': str(e)}
                )
                raise KubernetesOperationError(f'Prerequisites check failed: {str(e)}')
        
        @mcp_instance.tool()
        async def kubernetes_list_contexts(
            ctx: Context
        ) -> Dict[str, Any]:
            """List all available Kubernetes contexts from kubeconfig.
            
            Equivalent to: kubectl config get-contexts
            
            Returns:
                Dictionary containing:
                - 'contexts': List of context information dicts
                - 'current_context': Name of the currently active context
                - 'total_contexts': Total number of available contexts
            
            Raises:
                KubernetesOperationError: If listing contexts fails
            """
            await ctx.info('Listing Kubernetes contexts')
            
            await ctx.debug('Querying kubeconfig for available contexts')
            
            try:
                result = await self.k8s_service.list_contexts()
                
                current_context = result.get('current_context')
                total_contexts = result.get('total_contexts', 0)
                
                await ctx.info(
                    f"Found {total_contexts} context(s)",
                    extra={
                        'total_contexts': total_contexts,
                        'current_context': current_context,
                        'contexts': [c.get('name') for c in result.get('contexts', [])]
                    }
                )
                
                if current_context:
                    await ctx.debug(f"Current context: {current_context}")
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Failed to list contexts: {str(e)}",
                    extra={'error': str(e)}
                )
                raise KubernetesOperationError(f'Failed to list contexts: {str(e)}')
        
        @mcp_instance.tool()
        async def kubernetes_set_context(
            ctx: Context,
            context_name: str = Field(..., description='Name of the context to switch to')
        ) -> Dict[str, Any]:
            """Set/switch to a specific Kubernetes context.
            
            This loads the specified context from kubeconfig for use in the application.
            Note: This switches the context for the current application session only.
            
            Equivalent to: kubectl config use-context <context-name>
            
            Args:
                context_name: Name of the context to switch to
            
            Returns:
                Dictionary containing:
                - 'success': Boolean indicating if context was switched
                - 'context_name': Name of the context switched to
                - 'context_details': Dictionary with cluster, user, namespace info
                - 'message': Status message
            
            Raises:
                KubernetesOperationError: If context switching fails
            """
            await ctx.info(
                f"Switching to Kubernetes context '{context_name}'",
                extra={'context_name': context_name}
            )
            
            await ctx.debug('Validating context exists and loading configuration')
            
            try:
                result = await self.k8s_service.set_context(context_name)
                
                if result.get('success'):
                    context_details = result.get('context_details', {})
                    await ctx.info(
                        f"Successfully switched to context '{context_name}'",
                        extra={
                            'context_name': context_name,
                            'cluster': context_details.get('cluster'),
                            'user': context_details.get('user'),
                            'namespace': context_details.get('namespace')
                        }
                    )
                else:
                    await ctx.warning(
                        f"Context switch may not have succeeded: {result.get('message', 'Unknown error')}",
                        extra={'result': result}
                    )
                
                return result
            
            except Exception as e:
                await ctx.error(
                    f"Failed to set context: {str(e)}",
                    extra={
                        'context_name': context_name,
                        'error': str(e)
                    }
                )
                raise KubernetesOperationError(f'Failed to set context: {str(e)}')

