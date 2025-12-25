"""ArgoCD operations service - business logic layer."""

import json
import datetime
import urllib3
from typing import Optional, List, Dict, Any, Literal

import requests
import yaml
from kubernetes import client, config as k8s_config
from kubernetes.client.rest import ApiException

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.exceptions import (
    ArgoCDConnectionError,
    ArgoCDOperationError,
    ArgoCDNotFoundError,
    ArgoCDValidationError,
    RolloutOperationError,
    KubernetesOperationError,
    ArgoDBNotAvailable
)

# Suppress InsecureRequestWarning if using self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ArgoCDService:
    """Service for ArgoCD operations."""

    def __init__(self, config: ServerConfig):
        """Initialize with configuration."""
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            'Authorization': f'Bearer {self.config.argocd.auth_token}' if self.config.argocd.auth_token else '',
            'Content-Type': 'application/json'
        })
        self._session.verify = not self.config.argocd.insecure
        self.argocd_url = self.config.argocd.server_url.rstrip('/')
        
        # Initialize Kubernetes client if config provided
        self._init_k8s_client()

    def _init_k8s_client(self):
        """Initialize Kubernetes client."""
        try:
            if self.config.kubernetes.kubeconfig:
                k8s_config.load_kube_config(config_file=self.config.kubernetes.kubeconfig)
            else:
                k8s_config.load_incluster_config()
        except Exception as e:
            # We don't log here, but we could raise an initialization error if critical
            # For now, let's just intercept and maybe print to stderr if needed, or swallow as in original code logic but without logger.
            # However, requested instructions are to raise exceptions. Since this is init, failing silent or raising depends on "critical path".
            # The original code warned. We'll leave it silent or print simple message if debugging needed, but strict compliance means no logger.
            pass

    def _get_k8s_custom_objects_api(self):
        """Get Kubernetes CustomObjectsApi."""
        return client.CustomObjectsApi()

    def _request(self, method: str, path: str, is_json_response: bool = True, **kwargs) -> Any:
        """Make HTTP request to ArgoCD API."""
        url = f"{self.argocd_url}{path}"
        try:
            response = self._session.request(method, url, timeout=self.config.argocd.timeout, **kwargs)
            response.raise_for_status()
            
            if not is_json_response:
                return response.text
            
            # Check for JSON content type
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                return response.json()
            return response.text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ArgoCDNotFoundError(f"Resource not found: {url}")
            elif e.response.status_code == 401:
                raise ArgoCDConnectionError("Unauthorized: Invalid token")
            elif e.response.status_code >= 500:
                raise ArgoDBNotAvailable(f"ArgoCD server error: {str(e)}")
            else:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('message', str(e))
                except ValueError:
                    error_msg = str(e)
                raise ArgoCDOperationError(f"ArgoCD API error: {error_msg}")
        except requests.exceptions.ConnectionError as e:
            raise ArgoCDConnectionError(f"Failed to connect to ArgoCD: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise ArgoCDOperationError(f"Request failed: {str(e)}")

    def _check_write_access(self, operation: str, allow_dry_run: bool = False, dry_run: bool = False) -> None:
        """Check if write operations are allowed.
        
        Args:
            operation: Operation name for error message
            allow_dry_run: Whether dry-run operations are allowed without write access
            dry_run: Whether this is a dry-run operation
        
        Raises:
            ArgoCDOperationError: If write access is not allowed
        """
        if allow_dry_run and dry_run:
            # Dry-run operations don't need write access
            return
        
        if not self.config.allow_write:
            raise ArgoCDOperationError(
                f"ArgoCD {operation} is not allowed. "
                f"This MCP server is configured for read-only operations. "
                f"To enable write operations, set environment variable: MCP_ALLOW_WRITE=true"
            )

    async def list_applications(
        self,
        cluster_name: str,
        namespace: Optional[str] = None,
        project_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List all ArgoCD applications with pagination and filtering."""
        params = {}
        if project_filter:
            params['selector'] = f"proj=={project_filter}"
        
        try:
            data = self._request('GET', '/api/v1/applications', params=params)
            # ArgoCD API might return 'items': None when no applications exist
            items = data.get('items') or []
            
            filtered_apps = []
            for app in items:
                metadata = app.get('metadata', {})
                spec = app.get('spec', {})
                status = app.get('status', {})
                sync_status = status.get('sync', {}).get('status')
                
                # Check namespace filter
                if namespace and metadata.get('namespace') != namespace:
                    continue
                
                # Check status filter
                if status_filter and sync_status != status_filter:
                    continue
                
                filtered_apps.append({
                    'name': metadata.get('name'),
                    'namespace': metadata.get('namespace'),
                    'project': spec.get('project'),
                    'repo_url': spec.get('source', {}).get('repoURL'),
                    'target_revision': spec.get('source', {}).get('targetRevision'),
                    'sync_status': sync_status,
                    'health_status': status.get('health', {}).get('status'),
                    'last_sync_time': status.get('lastSyncResult', {}).get('finishedAt'),
                    'destination': {
                        'server': spec.get('destination', {}).get('server'),
                        'namespace': spec.get('destination', {}).get('namespace')
                    }
                })
            
            # Apply pagination manually if API doesn't support it for list
            total = len(filtered_apps)
            paginated_apps = filtered_apps[offset : offset + limit]
            
            result = {
                'total': total,
                'limit': limit,
                'offset': offset,
                'applications': paginated_apps,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }
            
            if total == 0:
                raise ArgoCDNotFoundError(
                    "No applications found. "
                    "To onboard a new application, please use the 'create_application' tool. "
                    "For detailed workflows and architectural guidelines, please read the "
                    "'argocd://workflow-architecture' resource."
                )

            return {
                'total': total,
                'limit': limit,
                'offset': offset,
                'applications': paginated_apps,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }
        except ArgoCDNotFoundError:
            raise
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to list applications: {str(e)}")

    async def get_application_details(
        self,
        cluster_name: str,
        app_name: str
    ) -> Dict[str, Any]:
        """Get detailed information about a specific ArgoCD application."""
        try:
            app = self._request('GET', f'/api/v1/applications/{app_name}')
            
            metadata = app.get('metadata', {})
            spec = app.get('spec', {})
            status = app.get('status', {})
            
            resources = []
            for res in status.get('resources', []):
                resources.append({
                    'group': res.get('group'),
                    'kind': res.get('kind'),
                    'namespace': res.get('namespace'),
                    'name': res.get('name'),
                    'status': res.get('status')
                })
                
            sync_history = []
            for sync in status.get('history', []):
                sync_history.append({
                    'revision': sync.get('revision'),
                    'author': sync.get('author'),
                    'message': sync.get('message'),
                    'timestamp': sync.get('timestamp'),
                    'status': sync.get('status')
                })
            
            sync_policy = spec.get('syncPolicy', {})
            automated = sync_policy.get('automated', {})
            
            return {
                'name': metadata.get('name'),
                'namespace': metadata.get('namespace'),
                'project': spec.get('project'),
                'source': {
                    'repo_url': spec.get('source', {}).get('repoURL'),
                    'path': spec.get('source', {}).get('path'),
                    'target_revision': spec.get('source', {}).get('targetRevision')
                },
                'destination': {
                    'server': spec.get('destination', {}).get('server'),
                    'namespace': spec.get('destination', {}).get('namespace')
                },
                'sync_policy': {
                    'automated': {
                        'prune': automated.get('prune') if automated else None,
                        'selfHeal': automated.get('selfHeal') if automated else None
                    }
                },
                'sync_status': status.get('sync', {}).get('status'),
                'health_status': status.get('health', {}).get('status'),
                'resources': resources,
                'sync_history': sync_history,
                'conditions': status.get('conditions', [])
            }
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Application '{app_name}' not found. "
                f"Use 'list_applications' to see available apps, or "
                f"'create_application' to onboard a new one if this is a new deployment."
            )
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get application details for '{app_name}': {str(e)}")

    async def create_application(
        self,
        cluster_name: str,
        app_name: str,
        project: str,
        repo_url: str,
        path: str,
        target_revision: str,
        destination_server: str,
        destination_namespace: str,
        auto_sync: bool = False,
        prune: bool = True,
        self_heal: bool = True
    ) -> Dict[str, Any]:
        """Create a new ArgoCD application."""
        # Check write access
        self._check_write_access('application creation')
        
        body = {
            "metadata": {"name": app_name},
            "spec": {
                "project": project,
                "source": {
                    "repoURL": repo_url,
                    "path": path,
                    "targetRevision": target_revision
                },
                "destination": {
                    "server": destination_server,
                    "namespace": destination_namespace
                }
            }
        }
        
        if auto_sync:
            body["spec"]["syncPolicy"] = {
                "automated": {
                    "prune": prune,
                    "selfHeal": self_heal
                }
            }
            
        try:
            self._request('POST', '/api/v1/applications', json=body)
            return {
                'name': app_name,
                'created': True,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'message': 'Application created successfully'
            }
        except Exception as e:
            if "already exists" in str(e).lower():
                raise ArgoCDOperationError(
                    f"Application '{app_name}' already exists. "
                    f"Use 'update_application' to modify its configuration, or "
                    f"'sync_application' to deploy changes."
                )
            raise ArgoCDOperationError(f"Failed to create application '{app_name}': {str(e)}")

    async def update_application(
        self,
        cluster_name: str,
        app_name: str,
        target_revision: Optional[str] = None,
        auto_sync: Optional[bool] = None,
        prune: Optional[bool] = None,
        self_heal: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update an existing ArgoCD application."""
        # Check write access
        self._check_write_access('application update')
        
        try:
            # First get the app
            app = self._request('GET', f'/api/v1/applications/{app_name}')
            spec = app.get('spec', {})
            
            if target_revision:
                if 'source' not in spec:
                    spec['source'] = {}
                spec['source']['targetRevision'] = target_revision
                
            if auto_sync is not None:
                if 'syncPolicy' not in spec:
                    spec['syncPolicy'] = {}
                
                if auto_sync:
                    if 'automated' not in spec['syncPolicy']:
                        spec['syncPolicy']['automated'] = {}
                    
                    if prune is not None:
                        spec['syncPolicy']['automated']['prune'] = prune
                    if self_heal is not None:
                        spec['syncPolicy']['automated']['selfHeal'] = self_heal
                else:
                    spec['syncPolicy'].pop('automated', None)
            
            app['spec'] = spec
            self._request('PUT', f'/api/v1/applications/{app_name}', json=app)
             
            return {
                'name': app_name,
                'updated': True,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'message': 'Application updated successfully'
            }
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Cannot update '{app_name}' because it does not exist. "
                f"Use 'create_application' to create it first."
            )
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to update application '{app_name}': {str(e)}")

    async def delete_application(
        self,
        cluster_name: str,
        app_name: str,
        cascade: bool = True
    ) -> Dict[str, Any]:
        """Delete an ArgoCD application."""
        # Check write access
        self._check_write_access('application deletion')
        
        params = {'cascade': str(cascade).lower()}
        try:
            self._request('DELETE', f'/api/v1/applications/{app_name}', params=params)
            return {
                'name': app_name,
                'deleted': True,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'message': 'Application deleted successfully'
            }
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Application '{app_name}' not found, so it may have already been deleted. "
                "No further action required."
            )
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to delete application '{app_name}': {str(e)}")

    async def sync_application(
        self,
        cluster_name: str,
        app_name: str,
        revision: Optional[str] = None,
        dry_run: bool = False,
        prune: bool = True,
        auto_policy: str = 'apply'
    ) -> Dict[str, Any]:
        """Sync an ArgoCD application to desired state."""
        # Check write access (dry-run is allowed without write access)
        self._check_write_access('application sync', allow_dry_run=True, dry_run=dry_run)
        
        body: Dict[str, Any] = {
            "dryRun": dry_run,
            "strategy": {"type": auto_policy}
        }
        
        if revision:
            body['revision'] = revision
        
        body['prune'] = prune
            
        try:
            result = self._request('POST', f'/api/v1/applications/{app_name}/sync', json=body)
            # Result usually contains operation info
            operation_state = result.get('status', {}).get('operationState', {})
            sync_info = operation_state.get('operation', {}).get('sync', {})
            
            message = "Sync operation initiated."
            if dry_run:
                message = "Dry-run sync performed successfully. No changes applied."
            
            return {
                'app_name': app_name,
                'status': operation_state.get('phase', 'Running'),
                'message': message,
                'details': {
                    'dry_run': dry_run,
                    'prune': prune,
                    'target_revision': sync_info.get('revision') or revision or 'HEAD',
                    'initiated_by': operation_state.get('operation', {}).get('initiatedBy', {}).get('username') or 'unknown'
                },
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Cannot sync '{app_name}' as it does not exist. "
                "Please ensure the application is created first."
            )
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to sync application '{app_name}': {str(e)}. "
                "Try running 'get_application_diff' to check for issues, "
                "or 'get_application_logs' if the sync started but failed."
            )

    async def get_application_diff(
        self,
        cluster_name: str,
        app_name: str,
        revision: Optional[str] = None,
        refresh: bool = True
    ) -> Dict[str, Any]:
        """Show what changes will happen before syncing."""
        try:
             # Standard ArgoCD API doesn't have a simple GET /diff endpoint that returns text.
             # We rely on refreshing the app and checking resource statuses.
             
             if refresh:
                 self._request('PUT', f'/api/v1/applications/{app_name}/refresh', params={'refresh': 'normal'})
                 
             app = self._request('GET', f'/api/v1/applications/{app_name}')
             
             status = app.get('status', {})
             resources = status.get('resources', [])
             
             diffs = []
             for res in resources:
                 if res.get('status') == 'OutOfSync':
                     diffs.append({
                         'group': res.get('group'),
                         'kind': res.get('kind'),
                         'name': res.get('name'),
                         'namespace': res.get('namespace'),
                         'status': res.get('status'),
                         'message': 'Resource is OutOfSync'
                     })
                     
             return {
                 'app_name': app_name,
                 'changes_detected': len(diffs) > 0,
                 'diffs': diffs,
                 'soure_revision': revision # Information only
             }
        except ArgoCDNotFoundError:
             raise ArgoCDNotFoundError(f"Application '{app_name}' not found. Cannot calculate diff.")
        except Exception as e:
             raise ArgoCDOperationError(f"Failed to get diff for '{app_name}': {str(e)}")

    async def validate_application_config(
        self,
        cluster_name: str,
        app_name: str
    ) -> Dict[str, Any]:
        """Validate application configuration using dry-run sync."""
        try:
            # Use dry-run sync to validate configuration
            await self.sync_application(
                cluster_name=cluster_name,
                app_name=app_name,
                dry_run=True,
                prune=True, # Check pruning too for full validation
                auto_policy='apply'
            )
            return {
                'valid': True,
                'error': None,
                'details': [],
                'message': 'Configuration validated successfully via dry-run sync.'
            }
        except Exception as e:
            # Check if it's a "not found" error specifically to re-raise, 
            # or treat as validation failure if it's a config issue?
            # The tool layer handles "not found" via looking at the exception type.
            # But here we are catching everything to return a dict? 
            # No, correct pattern is to let specific exceptions bubble up if they are "system" errors,
            # but catch "config" errors. 
            # However, distinguishing them is hard.
            # If the app is missing, sync_application raises ArgoCDNotFoundError.
            # We should let that bubble up so the tool can handle it with the "create app" advice.
            if isinstance(e, ArgoCDNotFoundError):
                raise
            
            # For other errors (manifest gen, etc), return as validation failure
            return {
                'valid': False,
                'error': str(e),
                'details': [str(e)],
                'message': f"Validation failed: {str(e)}"
            }

    async def get_application_resource_tree(
        self,
        cluster_name: str,
        app_name: str
    ) -> Dict[str, Any]:
        """Get the full resource tree of an application."""
        try:
            return self._request('GET', f'/api/v1/applications/{app_name}/resource-tree')
        except ArgoCDNotFoundError:
             raise ArgoCDNotFoundError(f"Application '{app_name}' not found.")
        except Exception as e:
             raise ArgoCDOperationError(f"Failed to get resource tree for '{app_name}': {str(e)}")

    async def get_application_events(
        self,
        cluster_name: str,
        app_name: str
    ) -> List[Dict[str, Any]]:
        """Get recent events for an application."""
        try:
            data = self._request('GET', f'/api/v1/applications/{app_name}/events')
            # items can be None if no events
            return data.get('items') or []
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get application events: {str(e)}")

    async def get_application_logs(
        self,
        cluster_name: str,
        app_name: str,
        pod_name: Optional[str] = None,
        container: Optional[str] = None,
        namespace: Optional[str] = None,
        tail: int = 50,
        since_seconds: Optional[int] = None,
        follow: bool = False
    ) -> str:
        """Get logs from application pods."""
        # Standard ArgoCD uses resource name to target logs
        params = {
            'tail': tail,
            'follow': str(follow).lower()
        }
        if pod_name:
            params['name'] = pod_name
        if container:
            params['container'] = container
        if namespace:
            params['namespace'] = namespace
        if since_seconds:
            params['sinceSeconds'] = since_seconds

        try:
            # Note: The correct endpoint path includes 'pods' and the pod name
            endpoint = f'/api/v1/applications/{app_name}/pods/{pod_name}/logs'
            
            # ArgoCD requires namespace as a parameter if not implicit
            if namespace:
                params['namespace'] = namespace
                
            return self._request('GET', endpoint, params=params, is_json_response=False)
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(f"Application '{app_name}' not found. Cannot retrieve logs.")
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to get logs for '{app_name}': {str(e)}. "
                "Ensure the deployment has created pods and they are not in a CrashLoopBackOff state "
                "without emitting logs."
            )

    async def get_sync_status(
        self,
        cluster_name: str,
        app_name: str
    ) -> Dict[str, Any]:
        """Get current sync status and operation progress."""
        try:
            # There is no dedicated /status endpoint in ArgoCD API.
            # Status is part of the Application resource.
            data = self._request('GET', f'/api/v1/applications/{app_name}')
            status = data.get('status', {})
            
            # Extract key information
            sync_status = status.get('sync', {})
            health_status = status.get('health', {})
            operation_state = status.get('operationState', {})
            history = status.get('history', [])
            
            # Format sync history (last 5 entries)
            formatted_history = []
            for item in history[-5:]:
                formatted_history.append({
                    'revision': item.get('revision'),
                    'deployed_at': item.get('deployedAt'),
                    'id': item.get('id'),
                    'initiated_by': item.get('initiatedBy', {}).get('username')
                })
            
            return {
                'app_name': app_name,
                'overall_sync_status': sync_status.get('status'),
                'health_status': health_status.get('status'),
                'sync_details': {
                    'revision': sync_status.get('revision'),
                    'compared_to': {
                        'source': sync_status.get('comparedTo', {}).get('source', {}).get('targetRevision'),
                        'destination': sync_status.get('comparedTo', {}).get('destination', {}).get('server')
                    }
                },
                'last_operation': {
                    'phase': operation_state.get('phase'),
                    'message': operation_state.get('message'),
                    'started_at': operation_state.get('startedAt'),
                    'finished_at': operation_state.get('finishedAt'),
                    'sync_result': operation_state.get('syncResult', {}).get('revision')
                },
                'sync_history': formatted_history
            }
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get sync status: {str(e)}")

    async def rollback_application(
        self,
        cluster_name: str,
        app_name: str,
        revision_id: int = -1,
        prune: bool = False
    ) -> Dict[str, Any]:
        """Rollback an application to previous revision."""
        # Check write access
        self._check_write_access('application rollback')
        
        body = {
            'id': revision_id,
            'prune': prune
        }
        try:
            return self._request('PUT', f'/api/v1/applications/{app_name}/rollback', json=body)
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(f"Application '{app_name}' not found. Cannot rollback.")
        except Exception as e:
            raise ArgoCDOperationError(
                f"Failed to rollback '{app_name}': {str(e)}. "
                "Use 'get_application_details' to check available history/revisions."
            )

    async def rollback_to_revision(
        self,
        cluster_name: str,
        app_name: str,
        revision: str
    ) -> Dict[str, Any]:
        """Rollback to a specific revision."""
        # Check write access
        self._check_write_access('application rollback to revision')
        
        # 'rollback-target' is not a standard endpoint. We reuse sync with revision.
        return await self.sync_application(
            cluster_name=cluster_name, 
            app_name=app_name, 
            revision=revision,
            prune=True,
            auto_policy='apply'
        )

    async def prune_resources(
        self,
        cluster_name: str,
        app_name: str,
        cascade: bool = False
    ) -> Dict[str, Any]:
        """Prune resources not in desired state."""
        # Check write access
        self._check_write_access('resource pruning')
        
        body = {'cascade': cascade}
        try:
            return self._request('DELETE', f'/api/v1/applications/{app_name}/resources', json=body)
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to prune resources: {str(e)}")

    async def hard_refresh(
        self,
        cluster_name: str,
        app_name: str
    ) -> Dict[str, Any]:
        """Hard refresh application (bypass cache)."""
        # Check write access
        self._check_write_access('application hard refresh')
        
        try:
            return self._request('PUT', f'/api/v1/applications/{app_name}/refresh', params={'refresh': 'hard'})
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to hard refresh: {str(e)}")

    async def soft_refresh(
        self,
        cluster_name: str,
        app_name: str
    ) -> Dict[str, Any]:
        """Soft refresh application state."""
        # Check write access
        self._check_write_access('application soft refresh')
        
        try:
            return self._request('PUT', f'/api/v1/applications/{app_name}/refresh', params={'refresh': 'normal'})
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to soft refresh: {str(e)}")

    async def cancel_deployment(
        self,
        cluster_name: str,
        app_name: str
    ) -> Dict[str, Any]:
        """Cancel ongoing sync operation."""
        # Check write access
        self._check_write_access('deployment cancellation')
        
        try:
            return self._request('DELETE', f'/api/v1/applications/{app_name}/operation')
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to cancel deployment: {str(e)}")
