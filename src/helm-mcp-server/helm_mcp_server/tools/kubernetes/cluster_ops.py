"""Kubernetes cluster inspection and operations tools."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from mcp.types import ToolAnnotations
from fastmcp import Context
from helm_mcp_server.exceptions import KubernetesOperationError
from helm_mcp_server.tools.base import BaseTool


class KubernetesTools(BaseTool):
    """Tools for Kubernetes cluster inspection and operations."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Kubernetes Cluster Info",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kubernetes_get_cluster_info(
            ctx: Context
        ) -> Dict[str, Any]:
            """Get Kubernetes cluster information.

            Use to verify cluster connectivity and view basic info
            (version, node count, namespace count). Read-only.

            Returns:
            - {"kubernetes_version": str, "node_count": int,
               "namespace_count": int, "nodes": [...]}

            When NOT to use:
            - To list namespaces → use kubernetes_list_namespaces.
            - To check prerequisites → use kubernetes_check_prerequisites.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Kubernetes Namespaces",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kubernetes_list_namespaces(
            ctx: Context
        ) -> List[str]:
            """List all Kubernetes namespaces in the current cluster.

            Use to discover available namespaces before installing
            or inspecting releases. Read-only.

            Returns:
            - List of namespace name strings: ["default", "kube-system", ...]

            When NOT to use:
            - To list Helm releases → use kubernetes_get_helm_releases.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Helm Releases in Cluster",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kubernetes_get_helm_releases(
            ctx: Context,
            namespace: Optional[str] = Field(default=None, description='Namespace filter (omit to list all namespaces)')
        ) -> List[Dict[str, Any]]:
            """List all Helm releases in the cluster.

            Use to discover what is already deployed before installing
            new releases. Optionally filter by namespace. Read-only.

            Returns:
            - List of release info dicts: [{"name": str, "namespace": str,
              "chart": str, "status": str, "revision": int}, ...]

            When NOT to use:
            - To get detailed status of one release → use helm_get_release_status.
            - To monitor a specific deployment → use helm_monitor_deployment.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Check Cluster Prerequisites",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kubernetes_check_prerequisites(
            ctx: Context,
            required_api_version: Optional[str] = Field(default=None, description='Required Kubernetes API version (e.g., "v1.28.0")'),
            required_resources: Optional[List[str]] = Field(default=None, description='Required resource types (e.g., ["Deployment", "Service", "Ingress"])')
        ) -> Dict[str, Any]:
            """Check if the cluster meets installation prerequisites.

            Use before installing a chart that requires specific K8s
            versions or CRD resource types. Read-only.

            Returns:
            - {"all_prerequisites_met": bool, "cluster_version": str,
               "api_version_check": {...}, "resource_check": {...}}

            When NOT to use:
            - To check chart dependencies → use helm_check_dependencies.
            - To get cluster info → use kubernetes_get_cluster_info.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Kubernetes Contexts",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def kubernetes_list_contexts(
            ctx: Context
        ) -> Dict[str, Any]:
            """List all available Kubernetes contexts from kubeconfig.

            Use to discover available clusters before switching context.
            Equivalent to: kubectl config get-contexts. Read-only.

            Returns:
            - {"contexts": [{"name": str, "cluster": str, "user": str,
               "namespace": str}], "current_context": str,
               "total_contexts": int}

            When NOT to use:
            - To switch context → use kubernetes_set_context.
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
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Set Kubernetes Context",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def kubernetes_set_context(
            ctx: Context,
            context_name: str = Field(..., description='Name of the context to switch to (from kubernetes_list_contexts)')
        ) -> Dict[str, Any]:
            """Switch to a specific Kubernetes context.

            Use to change the target cluster for subsequent operations.
            Switches context for the current application session only.
            Equivalent to: kubectl config use-context <context-name>.

            **NOTE: This changes the active cluster for ALL subsequent
            tool calls in this session.**

            Returns:
            - {"success": bool, "context_name": str,
               "context_details": {"cluster": str, "user": str,
               "namespace": str}, "message": str}

            When NOT to use:
            - To list available contexts → use kubernetes_list_contexts.
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
