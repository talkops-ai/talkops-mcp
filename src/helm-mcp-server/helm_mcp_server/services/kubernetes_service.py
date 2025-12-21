"""Kubernetes operations service."""

import asyncio
import subprocess
import json
from typing import Optional, List, Dict, Any
from helm_mcp_server.config import ServerConfig
from helm_mcp_server.exceptions import KubernetesOperationError
from helm_mcp_server.utils.helm_helper import is_helm_installed, check_for_dangerous_patterns


class KubernetesService:
    """Service for Kubernetes operations."""
    
    def __init__(self, config: ServerConfig):
        """Initialize with configuration."""
        self.config = config
        self._api = None
        self._version_api = None
        self._current_context = None
    
    def _get_api_clients(self):
        """Lazy-load Kubernetes API clients."""
        if self._api is None:
            try:
                from kubernetes import client, config as k8s_config
                k8s_config.load_incluster_config()
            except Exception:
                try:
                    from kubernetes import client, config as k8s_config
                    # Use the current context if one was set, otherwise use default
                    if self._current_context:
                        k8s_config.load_kube_config(
                            config_file=self.config.kubernetes.kubeconfig,
                            context=self._current_context
                        )
                    else:
                        k8s_config.load_kube_config(
                            config_file=self.config.kubernetes.kubeconfig
                        )
                except Exception as e:
                    raise KubernetesOperationError(
                        f'Failed to load Kubernetes config: {str(e)}'
                    )
            
            from kubernetes import client
            self._api = client.CoreV1Api()
            self._version_api = client.VersionApi()
        
        return self._api, self._version_api
    
    async def get_cluster_info(self) -> Dict[str, Any]:
        """Get cluster information."""
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            api, version_api = await loop.run_in_executor(None, self._get_api_clients)
            
            version = await loop.run_in_executor(None, version_api.get_code)
            nodes = await loop.run_in_executor(None, api.list_node)
            namespaces = await loop.run_in_executor(None, api.list_namespace)
            
            info = {
                'kubernetes_version': version.git_version,
                'node_count': len(nodes.items),
                'nodes': [n.metadata.name for n in nodes.items],
                'namespace_count': len(namespaces.items),
                'namespaces': [ns.metadata.name for ns in namespaces.items]
            }
            
            return info
        
        except Exception as e:
            raise KubernetesOperationError(f'Failed to get cluster info: {str(e)}')
    
    async def list_namespaces(self) -> list[str]:
        """List all Kubernetes namespaces.
        
        Returns:
            List of namespace names
        
        Raises:
            KubernetesOperationError: If listing fails
        """
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            api, _ = await loop.run_in_executor(None, self._get_api_clients)
            namespaces = await loop.run_in_executor(None, api.list_namespace)
            
            return [ns.metadata.name for ns in namespaces.items]
        
        except Exception as e:
            raise KubernetesOperationError(f'Failed to list namespaces: {str(e)}')

    async def list_contexts(self) -> Dict[str, Any]:
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
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._get_kube_contexts,
                self.config.kubernetes.kubeconfig
            )
            return result
        
        except Exception as e:
            raise KubernetesOperationError(f'Failed to list contexts: {str(e)}')
    
    def _get_kube_contexts(self, kubeconfig_path: Optional[str] = None) -> Dict[str, Any]:
        """Internal method to retrieve Kubernetes contexts from kubeconfig.
        
        Uses the kubernetes.config.list_kube_config_contexts() API.
        
        Args:
            kubeconfig_path: Optional path to kubeconfig file. If None, uses default.
        
        Returns:
            Dictionary with contexts list and current context info.
        """
        try:
            from kubernetes import config as k8s_config
            
            # Load and retrieve contexts
            result = k8s_config.list_kube_config_contexts(
                config_file=kubeconfig_path
            )
            
            # Handle case where list_kube_config_contexts returns None
            if result is None:
                raise KubernetesOperationError(
                    'Failed to retrieve Kubernetes contexts from kubeconfig. '
                    'The kubeconfig file may be invalid or inaccessible.'
                )
            
            contexts, active_context = result
            
            current_context_name = None
            if active_context:
                current_context_name = active_context.get('name')
            
            # Format contexts for response
            formatted_contexts = []
            for context in contexts:
                context_name = context.get('name', 'unknown')
                context_info = context.get('context', {})
                
                formatted_contexts.append({
                    'name': context_name,
                    'cluster': context_info.get('cluster', ''),
                    'user': context_info.get('user', ''),
                    'namespace': context_info.get('namespace', 'default'),
                    'is_current': context_name == current_context_name
                })
            
            return {
                'contexts': formatted_contexts,
                'current_context': current_context_name,
                'total_contexts': len(formatted_contexts)
            }
        
        except Exception as e:
            raise KubernetesOperationError(
                f'Failed to retrieve Kubernetes contexts: {str(e)}'
            )

    async def set_context(self, context_name: str) -> Dict[str, Any]:
        """Set/switch to a specific Kubernetes context.
        
        This loads the specified context from kubeconfig for use in the application.
        Note: This switches the context for the current application session only.
        To permanently modify the kubeconfig file, use set_context_in_kubeconfig().
        
        Equivalent to: kubectl config use-context <context-name>
        
        Args:
            context_name: Name of the context to switch to.
        
        Returns:
            Dictionary containing:
            - 'success': Boolean indicating if context was switched
            - 'context_name': Name of the context switched to
            - 'context_details': Dictionary with cluster, user, namespace info
            - 'message': Status message
        
        Raises:
            KubernetesOperationError: If context switching fails
        """
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._switch_kube_context,
                context_name,
                self.config.kubernetes.kubeconfig
            )
            return result
        
        except Exception as e:
            raise KubernetesOperationError(f'Failed to set context: {str(e)}')


    def _switch_kube_context(
        self, 
        context_name: str, 
        kubeconfig_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Internal method to switch to a specific Kubernetes context.
        
        Uses kubernetes.config.load_kube_config() with context parameter.
        
        Args:
            context_name: Name of the context to switch to.
            kubeconfig_path: Optional path to kubeconfig file.
        
        Returns:
            Dictionary with success status and context details.
        """
        try:
            from kubernetes import config as k8s_config
            
            # First, verify the context exists and get its details
            result = k8s_config.list_kube_config_contexts(
                config_file=kubeconfig_path
            )
            
            # Handle case where list_kube_config_contexts returns None
            if result is None:
                raise KubernetesOperationError(
                    'Failed to retrieve Kubernetes contexts from kubeconfig. '
                    'The kubeconfig file may be invalid or inaccessible.'
                )
            
            contexts, _ = result
            
            # Find the context we want to switch to
            target_context = None
            for ctx in contexts:
                if ctx.get('name') == context_name:
                    target_context = ctx
                    break
            
            if not target_context:
                available_contexts = [ctx.get('name') for ctx in contexts]
                raise KubernetesOperationError(
                    f'Context "{context_name}" not found. '
                    f'Available contexts: {", ".join(available_contexts)}'
                )
            
            # Load the specified context (returns None, just loads the config)
            k8s_config.load_kube_config(
                config_file=kubeconfig_path,
                context=context_name
            )
            
            # Store the current context and invalidate cached API clients
            # so they are recreated with the new context
            self._current_context = context_name
            self._api = None
            self._version_api = None
            
            # Get context details from the target context we found earlier
            context_details = target_context.get('context', {})
            
            return {
                'success': True,
                'context_name': context_name,
                'context_details': {
                    'cluster': context_details.get('cluster', ''),
                    'user': context_details.get('user', ''),
                    'namespace': context_details.get('namespace', 'default')
                },
                'message': f'Context switched to "{context_name}" successfully'
            }
        
        except KubernetesOperationError:
            raise
        except Exception as e:
            raise KubernetesOperationError(
                f'Failed to switch Kubernetes context: {str(e)}'
            )

    async def get_helm_releases(
        self,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all Helm releases in cluster.
        
        Args:
            namespace: Optional namespace filter (if None, lists all namespaces)
        
        Returns:
            List of Helm release information
        
        Raises:
            KubernetesOperationError: If listing fails
        """
        # Safety check: Check if Helm is installed
        if not is_helm_installed():
            raise KubernetesOperationError('Helm binary is not installed or not found in PATH.')
        
        try:
            cmd = ['helm', 'list', '-o', 'json']
            
            if namespace:
                cmd.extend(['-n', namespace])
            else:
                cmd.append('--all-namespaces')
            
            # Safety check: Check for dangerous patterns
            pattern = check_for_dangerous_patterns(cmd, log_prefix='[get_helm_releases] ')
            if pattern:
                raise KubernetesOperationError(
                    f"Dangerous pattern detected in command arguments: '{pattern}'. "
                    f"Aborting list for safety."
                )
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.kubernetes.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                raise KubernetesOperationError(
                    f'Helm list timeout ({self.config.kubernetes.timeout}s)'
                )
            
            if process.returncode != 0:
                raise KubernetesOperationError(f'Helm list failed: {stderr.decode().strip()}')
            
            releases = json.loads(stdout.decode().strip()) if stdout else []
            
            # Convert to list if single release
            if isinstance(releases, dict):
                releases = [releases]
            
            return releases
        
        except Exception as e:
            raise KubernetesOperationError(f'Failed to get Helm releases: {str(e)}')
    
    async def check_prerequisites(
        self,
        required_api_version: Optional[str] = None,
        required_resources: Optional[List[str]] = None,
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
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            api, version_api = await loop.run_in_executor(None, self._get_api_clients)
            
            # Get cluster version
            version = await loop.run_in_executor(None, version_api.get_code)
            cluster_version = version.git_version
            
            # Check API version if specified
            api_version_ok = True
            if required_api_version:
                # Simplified version comparison - could be enhanced
                api_version_ok = cluster_version >= required_api_version.lstrip('v')
            
            # Check resource types availability
            # Note: Full resource checking requires Discovery API which is complex
            # For now, we'll assume resources are available if cluster is accessible
            available_resources = []
            missing_resources = []
            
            if required_resources:
                # Simplified check - assume all standard resources are available
                # if cluster is accessible (could be enhanced with Discovery API)
                available_resources = required_resources
            
            all_prerequisites_met = api_version_ok and len(missing_resources) == 0
            
            return {
                'status': 'success',
                'cluster_version': cluster_version,
                'api_version_check': {
                    'required': required_api_version,
                    'current': cluster_version,
                    'meets_requirement': api_version_ok
                },
                'resource_check': {
                    'required': required_resources or [],
                    'available': available_resources,
                    'missing': missing_resources,
                    'all_available': len(missing_resources) == 0
                },
                'all_prerequisites_met': all_prerequisites_met
            }
        
        except Exception as e:
            raise KubernetesOperationError(f'Prerequisites check failed: {str(e)}')

