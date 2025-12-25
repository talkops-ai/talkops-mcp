"""ArgoCD Repository Management Service - business logic layer for repository onboarding."""

import json
import re
import base64
import datetime
import urllib3
from typing import Optional, Dict, Any, Literal
from enum import Enum

import requests

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.exceptions import (
    ArgoCDConnectionError,
    ArgoCDOperationError,
    ArgoCDNotFoundError,
    ArgoCDValidationError
)

# Suppress InsecureRequestWarning if using self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RepositoryType(Enum):
    """Supported repository types in ArgoCD"""
    GIT = "git"
    HELM = "helm"
    OCI = "oci"


class AuthMethod(Enum):
    """Supported authentication methods"""
    HTTPS_BASIC = "https_basic"
    HTTPS_TOKEN = "https_token"
    SSH_KEY = "ssh_key"
    GITHUB_APP = "github_app"
    TLS_CLIENT_CERT = "tls_client_cert"


class ArgoCDManagementService:
    """Service for ArgoCD repository management operations."""

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
                raise ArgoCDConnectionError(f"ArgoCD server error: {str(e)}")
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

    # ==================== REST API Methods ====================

    async def onboard_repository_https(
        self,
        repo_url: str,
        username: str,
        password: str,
        repo_type: RepositoryType = RepositoryType.GIT,
        enable_lfs: bool = False,
        project: Optional[str] = None,
        insecure: bool = False,
        force_http_basic_auth: bool = False
    ) -> Dict[str, Any]:
        """
        Onboard repository using HTTPS authentication (username/password or token).
        
        Args:
            repo_url: Repository URL (https://...)
            username: Git username (can be empty for token auth)
            password: Git password or personal access token
            repo_type: Repository type (git, helm, oci)
            enable_lfs: Enable Git LFS support
            project: Project-scoped repository
            insecure: Skip TLS certificate verification
            force_http_basic_auth: Force HTTP basic authentication
            
        Returns:
            dict: Repository object from ArgoCD API
            
        Raises:
            ValueError: Invalid input parameters
            ArgoCDOperationError: API request failed
        """
        # Check write access
        self._check_write_access('repository onboarding (HTTPS)')
        
        # Validate URL
        if not repo_url.startswith('https://'):
            raise ValueError("HTTPS repository URL must start with 'https://'")
        
        # Build repository configuration
        repo_config = {
            "repo": repo_url,
            "type": repo_type.value,
            "username": username,
            "password": password,
            "insecure": insecure
        }
        
        if enable_lfs:
            repo_config["enableLfs"] = enable_lfs
        if project:
            repo_config["project"] = project
        if force_http_basic_auth:
            repo_config["forceHttpBasicAuth"] = force_http_basic_auth
        
        # Call REST API
        return await self._create_repository_via_rest_api(repo_config)

    async def onboard_repository_ssh(
        self,
        repo_url: str,
        ssh_private_key: str,
        repo_type: RepositoryType = RepositoryType.GIT,
        enable_lfs: bool = False,
        project: Optional[str] = None,
        insecure_ignore_host_key: bool = False
    ) -> Dict[str, Any]:
        """
        Onboard repository using SSH authentication.
        
        Args:
            repo_url: Repository URL (ssh://... or git@...)
            ssh_private_key: SSH private key content (PEM format)
            repo_type: Repository type (git, helm, oci)
            enable_lfs: Enable Git LFS support
            project: Project-scoped repository
            insecure_ignore_host_key: Skip SSH host key verification (not recommended)
            
        Returns:
            dict: Repository object from ArgoCD API
            
        Raises:
            ValueError: Invalid input parameters
            ArgoCDOperationError: API request failed
        """
        # Check write access
        self._check_write_access('repository onboarding (SSH)')
        
        # Validate URL format)
        if not (repo_url.startswith('ssh://') or repo_url.startswith('git@')):
            raise ValueError("SSH repository URL must start with 'ssh://' or 'git@'")
        
        # Validate SSH key
        if not ssh_private_key or not ssh_private_key.strip():
            raise ValueError("SSH private key cannot be empty")
        
        # Build repository configuration
        repo_config = {
            "repo": repo_url,
            "type": repo_type.value,
            "sshPrivateKey": ssh_private_key
        }
        
        if enable_lfs:
            repo_config["enableLfs"] = enable_lfs
        if project:
            repo_config["project"] = project
        if insecure_ignore_host_key:
            repo_config["insecureIgnoreHostKey"] = insecure_ignore_host_key
        
        # Call REST API
        return await self._create_repository_via_rest_api(repo_config)

    async def _create_repository_via_rest_api(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create repository via REST API endpoint."""
        url_path = "/api/v1/repositories"
        
        try:
            response = self._request('POST', url_path, json=config)
            
            return {
                'repo_url': config.get('repo'),
                'type': config.get('type'),
                'created': True,
                'connection_state': response.get('connectionState', {}),
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'message': f"Repository '{config.get('repo')}' onboarded successfully",
                'raw_response': response
            }
            
        except ArgoCDOperationError as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                raise ArgoCDOperationError(
                    f"Repository '{config.get('repo')}' already exists. "
                    "Use 'get_repository' to view its configuration, or "
                    "'update_repository' to modify it."
                )
            raise ArgoCDOperationError(f"Failed to create repository: {error_msg}")

    async def list_repositories(
        self,
        repo_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all repositories in ArgoCD.
        
        Args:
            repo_filter: Optional URL filter to search for specific repository
            
        Returns:
            dict: List of repository objects with metadata
        """
        url_path = "/api/v1/repositories"
        
        try:
            response = self._request('GET', url_path)
            
            # ArgoCD API might return 'items': None when no repositories exist
            items = response.get('items') or []
            
            # Apply filter if provided
            if repo_filter:
                items = [
                    repo for repo in items 
                    if repo_filter.lower() in repo.get('repo', '').lower()
                ]
            
            # Format response
            repositories = []
            for repo in items:
                repositories.append({
                    'repo': repo.get('repo'),
                    'type': repo.get('type'),
                    'name': repo.get('name'),
                    'project': repo.get('project'),
                    'connection_state': repo.get('connectionState', {}),
                    'username': repo.get('username'),
                    'insecure': repo.get('insecure', False),
                    'enable_lfs': repo.get('enableLfs', False)
                })
            
            return {
                'total': len(repositories),
                'repositories': repositories,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }
            
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to list repositories: {str(e)}")

    async def get_repository(
        self,
        repo_url: str
    ) -> Dict[str, Any]:
        """
        Get repository details by URL.
        
        Args:
            repo_url: Repository URL (must match registered URL exactly)
            
        Returns:
            dict: Repository object with full details
        """
        # URL-encode the repo URL for API request
        encoded_url = requests.utils.quote(repo_url, safe='')
        url_path = f"/api/v1/repositories/{encoded_url}"
        
        try:
            response = self._request('GET', url_path)
            
            return {
                'repo': response.get('repo'),
                'type': response.get('type'),
                'name': response.get('name'),
                'project': response.get('project'),
                'connection_state': response.get('connectionState', {}),
                'username': response.get('username'),
                'insecure': response.get('insecure', False),
                'enable_lfs': response.get('enableLfs', False),
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }
            
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Repository '{repo_url}' not found. "
                "Use 'list_repositories' to see all registered repositories."
            )
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get repository: {str(e)}")

    async def validate_repository_connection(
        self,
        repo_url: str,
        auth_method: AuthMethod,
        **auth_config
    ) -> Dict[str, Any]:
        """
        Validate repository connection without storing it.
        
        Args:
            repo_url: Repository URL to validate
            auth_method: Authentication method
            **auth_config: Authentication configuration (method-specific)
            
        Returns:
            dict: Validation result with connection status
        """
        # Build repository configuration based on auth method
        repo_config = {
            "repo": repo_url,
            "type": "git"  # Default to git for validation
        }
        
        # Add authentication based on method
        if auth_method == AuthMethod.HTTPS_BASIC or auth_method == AuthMethod.HTTPS_TOKEN:
            repo_config["username"] = auth_config.get("username", "")
            repo_config["password"] = auth_config.get("password", "")
        elif auth_method == AuthMethod.SSH_KEY:
            repo_config["sshPrivateKey"] = auth_config.get("ssh_private_key", "")
            if "insecure_ignore_host_key" in auth_config:
                repo_config["insecureIgnoreHostKey"] = auth_config["insecure_ignore_host_key"]
        
        # Add other optional configs
        if "insecure" in auth_config:
            repo_config["insecure"] = auth_config["insecure"]
        
        url_path = "/api/v1/repositories/validate"
        
        try:
            response = self._request('POST', url_path, json=repo_config)
            
            return {
                'valid': True,
                'repo_url': repo_url,
                'connection_state': response.get('connectionState', {}),
                'message': 'Repository connection validated successfully',
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }
            
        except ArgoCDOperationError as e:
            return {
                'valid': False,
                'repo_url': repo_url,
                'error': str(e),
                'message': f'Repository validation failed: {str(e)}',
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }

    async def delete_repository(
        self,
        repo_url: str
    ) -> Dict[str, Any]:
        """
        Delete a registered repository.
        
        Args:
            repo_url: Repository URL to delete
            
        Returns:
            dict: Success message
            
        Raises:
            ArgoCDNotFoundError: Repository not found
            ArgoCDOperationError: Delete operation failed
        """
        # Check write access
        self._check_write_access('repository deletion')
        
        # URL-encode the repo URL
        encoded_url = requests.utils.quote(repo_url, safe='')
        url_path = f"/api/v1/repositories/{encoded_url}"
        
        try:
            self._request('DELETE', url_path)
            
            return {
                'repo_url': repo_url,
                'deleted': True,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'message': f"Repository '{repo_url}' deleted successfully"
            }
            
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Repository '{repo_url}' not found, so it may have already been deleted. "
                "No further action required."
            )
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to delete repository '{repo_url}': {str(e)}")

    # ==================== Kubernetes Secret Methods ====================

    async def generate_repository_secret_manifest(
        self,
        repo_url: str,
        auth_method: AuthMethod,
        secret_name: Optional[str] = None,
        namespace: str = "argocd",
        repo_type: RepositoryType = RepositoryType.GIT,
        enable_lfs: bool = False,
        project: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        **auth_config
    ) -> Dict[str, Any]:
        """
        Generate Kubernetes Secret YAML manifest for repository (Declarative setup).
        
        Args:
            repo_url: Repository URL
            auth_method: Authentication method
            secret_name: Optional Kubernetes secret name (auto-generated if not provided)
            namespace: Kubernetes namespace (default: argocd)
            repo_type: Repository type
            enable_lfs: Enable Git LFS support
            project: Project-scoped repository
            labels: Additional labels for the secret
            **auth_config: Authentication configuration (method-specific)
            
        Returns:
            dict: Kubernetes Secret object (YAML-ready)
        """
        # Generate secret name if not provided
        if not secret_name:
            secret_name = self._generate_secret_name(repo_url)
        
        # Build string data
        string_data = {
            "type": repo_type.value,
            "url": repo_url,
        }
        
        # Add authentication data
        string_data.update(self._build_auth_string_data(auth_method, auth_config))
        
        # Add optional settings
        if enable_lfs:
            string_data["enableLfs"] = "true"
        if project:
            string_data["project"] = project
        
        # Build labels
        default_labels = {
            "argocd.argoproj.io/secret-type": "repository"
        }
        if labels:
            default_labels.update(labels)
        
        # Build secret object
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": secret_name,
                "namespace": namespace,
                "labels": default_labels
            },
            "stringData": string_data
        }
        
        return {
            'secret_name': secret_name,
            'namespace': namespace,
            'repo_url': repo_url,
            'manifest': secret,
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
            'message': f"Generated Kubernetes secret manifest for repository '{repo_url}'"
        }

    @staticmethod
    def _generate_secret_name(repo_url: str) -> str:
        """Generate Kubernetes-compatible secret name from repo URL."""
        # Extract meaningful part from URL
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        # Make Kubernetes-compatible (lowercase, no special chars except dash)
        safe_name = re.sub(r'[^a-z0-9-]', '-', repo_name.lower())
        safe_name = re.sub(r'-+', '-', safe_name).strip('-')
        return f"repo-{safe_name}"

    def _build_auth_string_data(
        self,
        auth_method: AuthMethod,
        auth_config: Dict[str, Any]
    ) -> Dict[str, str]:
        """Build authentication string data for Kubernetes secret."""
        
        string_data = {}
        
        if auth_method == AuthMethod.HTTPS_BASIC:
            string_data["username"] = auth_config.get("username", "")
            string_data["password"] = auth_config.get("password", "")
            if "force_http_basic_auth" in auth_config:
                string_data["forceHttpBasicAuth"] = str(auth_config["force_http_basic_auth"]).lower()
                
        elif auth_method == AuthMethod.HTTPS_TOKEN:
            string_data["password"] = auth_config.get("token", "")
            if "username" in auth_config:
                string_data["username"] = auth_config["username"]
                
        elif auth_method == AuthMethod.SSH_KEY:
            string_data["sshPrivateKey"] = auth_config.get("ssh_private_key", "")
            if "insecure_ignore_host_key" in auth_config:
                string_data["insecureIgnoreHostKey"] = str(auth_config["insecure_ignore_host_key"]).lower()
                
        elif auth_method == AuthMethod.GITHUB_APP:
            string_data["githubAppID"] = str(auth_config.get("github_app_id", ""))
            string_data["githubAppInstallationID"] = str(auth_config.get("github_app_installation_id", ""))
            string_data["githubAppPrivateKey"] = auth_config.get("github_app_private_key", "")
            
        elif auth_method == AuthMethod.TLS_CLIENT_CERT:
            string_data["tlsClientCertData"] = auth_config.get("tls_client_cert_data", "")
            string_data["tlsClientCertKey"] = auth_config.get("tls_client_cert_key", "")
        
        # Add insecure flag if present
        if "insecure" in auth_config:
            string_data["insecure"] = str(auth_config["insecure"]).lower()
        
        return string_data

    # ==================== Project Management Methods ====================

    async def create_project(
        self,
        project_name: str,
        description: str,
        source_repos: list[str],
        destinations: list[Dict[str, str]],
        cluster_resource_whitelist: Optional[list[Dict[str, str]]] = None,
        cluster_resource_blacklist: Optional[list[Dict[str, str]]] = None,
        namespace_resource_whitelist: Optional[list[Dict[str, str]]] = None,
        namespace_resource_blacklist: Optional[list[Dict[str, str]]] = None,
        orphaned_resources_warn: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new ArgoCD project.
        
        Args:
            project_name: Project name
            description: Project description
            source_repos: Allowed source repositories (wildcards supported, e.g., https://github.com/org/*)
            destinations: Allowed destination clusters and namespaces
            cluster_resource_whitelist: Allowed cluster-level resources
            cluster_resource_blacklist: Denied cluster-level resources
            namespace_resource_whitelist: Allowed namespace-scoped resources
            namespace_resource_blacklist: Denied namespace-scoped resources
            
        Returns:
            dict: Created project object
            
        Raises:
            ArgoCDValidationError: Validation failed
            ArgoCDOperationError: Create operation failed
        """
        # Check write access
        self._check_write_access('project creation')
        
        # Validate inputsroject name
        if not project_name or not project_name.strip():
            raise ValueError("Project name cannot be empty")
        
        # Build project spec
        project_spec = {
            "sourceRepos": source_repos,
            "destinations": destinations
        }
        
        # Add optional resource restrictions
        if cluster_resource_whitelist:
            project_spec["clusterResourceWhitelist"] = cluster_resource_whitelist
        if cluster_resource_blacklist:
            project_spec["clusterResourceBlacklist"] = cluster_resource_blacklist
        if namespace_resource_whitelist:
            project_spec["namespaceResourceWhitelist"] = namespace_resource_whitelist
        if namespace_resource_blacklist:
            project_spec["namespaceResourceBlacklist"] = namespace_resource_blacklist
        
        # Add orphaned resources configuration
        if orphaned_resources_warn:
            project_spec["orphanedResources"] = {"warn": True}
        
        # Build full project object
        project = {
            "metadata": {
                "name": project_name
            },
            "spec": project_spec
        }
        
        # Add description as annotation
        if description:
            project["metadata"]["annotations"] = {
                "description": description
            }
        
        url_path = "/api/v1/projects"
        
        try:
            # ArgoCD API expects the project to be wrapped in a "project" key
            response = self._request('POST', url_path, json={"project": project})
            
            return {
                'project_name': project_name,
                'created': True,
                'source_repos': source_repos,
                'destinations': destinations,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'message': f"Project '{project_name}' created successfully",
                'raw_response': response
            }
            
        except ArgoCDOperationError as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                raise ArgoCDOperationError(
                    f"Project '{project_name}' already exists. "
                    "Use 'get_project' to view its configuration."
                )
            raise ArgoCDOperationError(f"Failed to create project: {error_msg}")

    async def list_projects(
        self,
        name_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all ArgoCD projects.
        
        Args:
            name_filter: Optional name filter to search for specific projects
            
        Returns:
            dict: List of project objects with metadata
        """
        url_path = "/api/v1/projects"
        
        try:
            response = self._request('GET', url_path)
            
            # ArgoCD API might return 'items': None when no projects exist
            items = response.get('items') or []
            
            # Apply filter if provided
            if name_filter:
                items = [
                    proj for proj in items
                    if name_filter.lower() in proj.get('metadata', {}).get('name', '').lower()
                ]
            
            # Format response
            projects = []
            for proj in items:
                metadata = proj.get('metadata', {})
                spec = proj.get('spec', {})
                
                projects.append({
                    'name': metadata.get('name'),
                    'description': metadata.get('annotations', {}).get('description', ''),
                    'source_repos': spec.get('sourceRepos', []),
                    'destinations': spec.get('destinations', []),
                    'cluster_resource_whitelist': spec.get('clusterResourceWhitelist'),
                    'cluster_resource_blacklist': spec.get('clusterResourceBlacklist')
                })
            
            return {
                'total': len(projects),
                'projects': projects,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
            }
            
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to list projects: {str(e)}")

    async def get_project(
        self,
        project_name: str
    ) -> Dict[str, Any]:
        """
        Get project details by name.
        
        Args:
            project_name: Project name
            
        Returns:
            dict: Project object with full details
        """
        url_path = f"/api/v1/projects/{project_name}"
        
        try:
            response = self._request('GET', url_path)
            
            metadata = response.get('metadata', {})
            spec = response.get('spec', {})
            
            return {
                'name': metadata.get('name'),
                'description': metadata.get('annotations', {}).get('description', ''),
                'source_repos': spec.get('sourceRepos', []),
                'destinations': spec.get('destinations', []),
                'cluster_resource_whitelist': spec.get('clusterResourceWhitelist'),
                'cluster_resource_blacklist': spec.get('clusterResourceBlacklist'),
                'namespace_resource_whitelist': spec.get('namespaceResourceWhitelist'),
                'namespace_resource_blacklist': spec.get('namespaceResourceBlacklist'),
                'orphaned_resources': spec.get('orphanedResources'),
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'raw_response': response
            }
            
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Project '{project_name}' not found. "
                "Use 'list_projects' to see all available projects."
            )
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get project: {str(e)}")

    async def delete_project(
        self,
        project_name: str
    ) -> Dict[str, Any]:
        """
        Delete an ArgoCD project.
        
        Args:
            project_name: Project name to delete
            
        Returns:
            dict: Success message
            
        Raises:
            ArgoCDNotFoundError: Project not found
            ArgoCDOperationError: Delete operation failed
        """
        # Check write access
        self._check_write_access('project deletion')
        
        url_path = f"/api/v1/projects/{project_name}"
        
        try:
            self._request('DELETE', url_path)
            
            return {
                'project_name': project_name,
                'deleted': True,
                'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
                'message': f"Project '{project_name}' deleted successfully"
            }
            
        except ArgoCDNotFoundError:
            raise ArgoCDNotFoundError(
                f"Project '{project_name}' not found, so it may have already been deleted. "
                "No further action required."
            )
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to delete project '{project_name}': {str(e)}")

    async def generate_project_manifest(
        self,
        project_name: str,
        description: str,
        source_repos: list[str],
        destinations: list[Dict[str, str]],
        namespace: str = "argocd",
        cluster_resource_whitelist: Optional[list[Dict[str, str]]] = None,
        cluster_resource_blacklist: Optional[list[Dict[str, str]]] = None,
        namespace_resource_whitelist: Optional[list[Dict[str, str]]] = None,
        namespace_resource_blacklist: Optional[list[Dict[str, str]]] = None,
        orphaned_resources_warn: bool = False,
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Generate Kubernetes AppProject manifest for declarative setup.
        
        Args:
            project_name: Project name
            description: Project description
            source_repos: List of source repository URLs (supports wildcards)
            destinations: List of destination clusters and namespaces
            namespace: Kubernetes namespace (default: argocd)
            cluster_resource_whitelist: Allowed cluster-scoped resources
            cluster_resource_blacklist: Denied cluster-scoped resources
            namespace_resource_whitelist: Allowed namespace-scoped resources
            namespace_resource_blacklist: Denied namespace-scoped resources
            orphaned_resources_warn: Warn about orphaned resources
            labels: Additional labels for the project
            
        Returns:
            dict: Kubernetes AppProject object (YAML-ready)
        """
        # Build metadata
        metadata = {
            "name": project_name,
            "namespace": namespace
        }
        
        if description:
            metadata["annotations"] = {"description": description}
        
        if labels:
            metadata["labels"] = labels
        
        # Build spec
        spec = {
            "sourceRepos": source_repos,
            "destinations": destinations
        }
        
        # Add optional resource restrictions
        if cluster_resource_whitelist:
            spec["clusterResourceWhitelist"] = cluster_resource_whitelist
        if cluster_resource_blacklist:
            spec["clusterResourceBlacklist"] = cluster_resource_blacklist
        if namespace_resource_whitelist:
            spec["namespaceResourceWhitelist"] = namespace_resource_whitelist
        if namespace_resource_blacklist:
            spec["namespaceResourceBlacklist"] = namespace_resource_blacklist
        
        # Add orphaned resources configuration
        if orphaned_resources_warn:
            spec["orphanedResources"] = {"warn": True}
        
        # Build AppProject object
        app_project = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "AppProject",
            "metadata": metadata,
            "spec": spec
        }
        
        return {
            'project_name': project_name,
            'namespace': namespace,
            'manifest': app_project,
            'timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
            'message': f"Generated AppProject manifest for '{project_name}'"
        }
