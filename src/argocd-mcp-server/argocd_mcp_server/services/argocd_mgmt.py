"""ArgoCD Repository and Project Management Service."""

import os
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit

import httpx

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.exceptions import (
    ArgoCDConflictError,
    ArgoCDConnectionError,
    ArgoCDNotFoundError,
    ArgoCDOperationError,
    ArgoCDPermissionError,
)
from argocd_mcp_server.services.argocd_client import ArgoCDClient


class RepositoryType(Enum):
    """Supported repository types in ArgoCD."""
    GIT = "git"
    HELM = "helm"
    OCI = "oci"


class AuthMethod(Enum):
    """Supported authentication methods."""
    HTTPS_BASIC = "https_basic"
    HTTPS_TOKEN = "https_token"
    SSH_KEY = "ssh_key"
    GITHUB_APP = "github_app"
    TLS_CLIENT_CERT = "tls_client_cert"


class ArgoCDManagementService:
    """Service for ArgoCD repository and AppProject management operations."""

    def __init__(self, config: ServerConfig, client: Optional[ArgoCDClient] = None):
        """Initialize with configuration and optional shared ArgoCDClient."""
        self.config = config
        self.client = client or ArgoCDClient(config)
        self.argocd_url = self.client.argocd_url

    def _check_write_access(
        self,
        operation: str,
        allow_dry_run: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Check if write operations are allowed."""
        self.client.check_write_access(
            operation=operation,
            allow_dry_run=allow_dry_run,
            dry_run=dry_run,
        )

    @staticmethod
    def infer_url_scheme(repo_url: str) -> str:
        """Infer 'https' or 'ssh' from repository URL and reject embedded credentials."""
        url = (repo_url or "").strip()
        if url.startswith("https://"):
            parsed = urlsplit(url)
            if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
                raise ValueError(
                    "Embedded credentials in repo_url are prohibited. "
                    "Pass a clean repository URL and configure GIT_USERNAME/GIT_PASSWORD on the server."
                )
            return "https"
        if url.startswith("ssh://") or url.startswith("git@"):
            return "ssh"
        raise ValueError(
            f"Unsupported repository URL format '{repo_url}'. "
            "URL must start with 'https://', 'ssh://', or 'git@'."
        )

    def _resolve_server_credentials(self, scheme: str) -> Dict[str, str]:
        """Resolve Git credentials from server configuration (never from LLM args)."""
        if scheme == "https":
            return {
                "username": self.config.git.username or "",
                "password": self.config.git.password or "",
            }

        ssh_key_path = os.path.expanduser(self.config.git.ssh_private_key_path)
        if not os.path.exists(ssh_key_path):
            raise FileNotFoundError(
                f"SSH private key file not found at '{ssh_key_path}'. "
                "Configure SSH_PRIVATE_KEY_PATH in the server environment."
            )
        with open(ssh_key_path, "r", encoding="utf-8") as f:
            ssh_private_key = f.read()
        if not ssh_private_key.strip():
            raise ValueError(f"SSH private key file at '{ssh_key_path}' is empty.")
        return {"ssh_private_key": ssh_private_key}

    async def onboard_repository(
        self,
        repo_url: str,
        repo_type: str = "git",
        project: Optional[str] = None,
        enable_lfs: bool = False,
        insecure: bool = False,
        force_http_basic_auth: bool = False,
    ) -> Dict[str, Any]:
        """Onboard a repository using URL-inferred auth and server-side credentials."""
        self._check_write_access("repository onboarding")

        scheme = self.infer_url_scheme(repo_url)
        try:
            repo_type_enum = RepositoryType(repo_type.lower())
        except ValueError as e:
            raise ValueError(
                f"Invalid repo_type '{repo_type}'. Must be one of: git, helm, oci."
            ) from e

        creds = self._resolve_server_credentials(scheme)

        if scheme == "https":
            return await self.onboard_repository_https(
                repo_url=repo_url,
                username=creds["username"],
                password=creds["password"],
                repo_type=repo_type_enum,
                enable_lfs=enable_lfs,
                project=project,
                insecure=insecure,
                force_http_basic_auth=force_http_basic_auth,
            )
        return await self.onboard_repository_ssh(
            repo_url=repo_url,
            ssh_private_key=creds["ssh_private_key"],
            repo_type=repo_type_enum,
            enable_lfs=enable_lfs,
            project=project,
            insecure_ignore_host_key=insecure,
        )

    async def onboard_repository_https(
        self,
        repo_url: str,
        username: str,
        password: str,
        repo_type: RepositoryType = RepositoryType.GIT,
        enable_lfs: bool = False,
        project: Optional[str] = None,
        insecure: bool = False,
        force_http_basic_auth: bool = False,
    ) -> Dict[str, Any]:
        """Onboard repository using HTTPS authentication."""
        self._check_write_access("repository onboarding (HTTPS)")

        if not repo_url.startswith("https://"):
            raise ValueError("HTTPS repository URL must start with 'https://'")

        repo_config: Dict[str, Any] = {
            "repo": repo_url,
            "type": repo_type.value if isinstance(repo_type, RepositoryType) else str(repo_type),
            "insecure": insecure,
        }
        if username:
            repo_config["username"] = username
        if password:
            repo_config["password"] = password
        if enable_lfs:
            repo_config["enableLfs"] = enable_lfs
        if project:
            repo_config["project"] = project
        if force_http_basic_auth:
            repo_config["forceHttpBasicAuth"] = force_http_basic_auth

        return await self._create_repository_via_rest_api(repo_config, auth_mode="https")

    async def onboard_repository_ssh(
        self,
        repo_url: str,
        ssh_private_key: str,
        repo_type: RepositoryType = RepositoryType.GIT,
        enable_lfs: bool = False,
        project: Optional[str] = None,
        insecure_ignore_host_key: bool = False,
    ) -> Dict[str, Any]:
        """Onboard repository using SSH authentication."""
        self._check_write_access("repository onboarding (SSH)")

        if not (repo_url.startswith("ssh://") or repo_url.startswith("git@")):
            raise ValueError("SSH repository URL must start with 'ssh://' or 'git@'")
        if not ssh_private_key or not ssh_private_key.strip():
            raise ValueError("SSH private key cannot be empty")

        repo_config: Dict[str, Any] = {
            "repo": repo_url,
            "type": repo_type.value if isinstance(repo_type, RepositoryType) else str(repo_type),
            "sshPrivateKey": ssh_private_key,
        }
        if enable_lfs:
            repo_config["enableLfs"] = enable_lfs
        if project:
            repo_config["project"] = project
        if insecure_ignore_host_key:
            repo_config["insecureIgnoreHostKey"] = insecure_ignore_host_key

        return await self._create_repository_via_rest_api(repo_config, auth_mode="ssh")

    async def _create_repository_via_rest_api(
        self, config: Dict[str, Any], auth_mode: str = "https"
    ) -> Dict[str, Any]:
        """Create repository via REST API endpoint and return sanitized summary."""
        try:
            response = await self.client.request("POST", "/api/v1/repositories", json=config)
            conn_state = (response.get("connectionState") if isinstance(response, dict) else None) or {}
            resolved_status = conn_state.get("status") or "Successful"
            return {
                "repo_url": config.get("repo"),
                "type": config.get("type"),
                "auth_mode": auth_mode,
                "project": config.get("project"),
                "created": True,
                "connection_status": resolved_status,
                "connection_state": {
                    "status": resolved_status,
                    "message": conn_state.get("message", ""),
                },
                "message": f"Repository '{config.get('repo')}' onboarded successfully ({auth_mode.upper()}).",
            }
        except (ArgoCDConflictError, ArgoCDOperationError) as e:
            if isinstance(e, ArgoCDConflictError) or "already exists" in str(e).lower():
                raise ArgoCDOperationError(
                    f"Repository '{config.get('repo')}' is already registered in ArgoCD. "
                    "Call 'get_repository' to inspect its connection state."
                ) from e
            raise ArgoCDOperationError(f"Failed to onboard repository: {str(e)}") from e

    async def list_repositories(
        self,
        repo_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List all repositories registered in ArgoCD with credentials redacted."""
        try:
            response = await self.client.request("GET", "/api/v1/repositories")
            items = (response.get("items") if isinstance(response, dict) else None) or []

            if repo_filter:
                items = [
                    r for r in items if repo_filter.lower() in (r.get("repo") or "").lower()
                ]

            repositories = [
                {
                    "repo": r.get("repo"),
                    "type": r.get("type", "git"),
                    "project": r.get("project") or "default",
                    "connection_status": (r.get("connectionState") or {}).get("status", "Unknown"),
                    "insecure": bool(r.get("insecure", False)),
                }
                for r in items
            ]
            return {
                "total": len(repositories),
                "repositories": repositories,
            }
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to list repositories: {str(e)}") from e

    async def get_repository(self, repo_url: str) -> Dict[str, Any]:
        """Get repository connection status and metadata (credentials redacted)."""
        encoded_url = quote(repo_url, safe="")
        try:
            response = await self.client.request("GET", f"/api/v1/repositories/{encoded_url}")
            conn = (response.get("connectionState") if isinstance(response, dict) else None) or {}
            return {
                "repo": response.get("repo", repo_url),
                "type": response.get("type", "git"),
                "project": response.get("project") or "default",
                "connection_status": conn.get("status", "Unknown"),
                "connection_state": {
                    "status": conn.get("status", "Unknown"),
                    "message": conn.get("message", ""),
                },
                "insecure": bool(response.get("insecure", False)),
                "enable_lfs": bool(response.get("enableLfs", False)),
            }
        except ArgoCDNotFoundError as e:
            raise ArgoCDNotFoundError(
                f"Repository '{repo_url}' not found in ArgoCD. "
                "Call 'list_repositories' to see registered repositories or 'onboard_repository' to add it."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get repository '{repo_url}': {str(e)}") from e

    async def _probe_https_repository(
        self,
        repo_url: str,
        username: str = "",
        password: str = "",
        insecure: bool = False,
    ) -> Dict[str, Any]:
        """Probe remote HTTPS Git or Helm repository reachability when ArgoCD REST /validate returns 405."""
        base = repo_url.rstrip("/")
        auth = (username or "git", password) if password else None
        probe_urls = (
            [f"{base}/info/refs?service=git-upload-pack"]
            if base.endswith(".git")
            else [
                f"{base}/index.yaml",
                f"{base}/info/refs?service=git-upload-pack",
                f"{base}.git/info/refs?service=git-upload-pack",
            ]
        )
        last_status: Optional[int] = None
        async with httpx.AsyncClient(
            verify=not insecure,
            follow_redirects=True,
            timeout=15.0,
        ) as http_client:
            for p_url in probe_urls:
                resp = await http_client.get(p_url, auth=auth)
                last_status = resp.status_code
                if resp.status_code == 200:
                    return {"status": "Successful"}
                if resp.status_code in (401, 403):
                    raise ArgoCDPermissionError(
                        f"Authentication required ({resp.status_code}) accessing '{repo_url}'. "
                        "Configure GIT_USERNAME and GIT_PASSWORD on the MCP server."
                    )
        if not password and last_status == 404:
            raise ArgoCDNotFoundError(
                f"Repository '{repo_url}' returned HTTP 404 (not found or private repository requiring GIT_PASSWORD)."
            )
        raise ArgoCDOperationError(
            f"Repository probe for '{repo_url}' returned HTTP {last_status}."
        )

    async def validate_repository_connection(
        self,
        repo_url: str,
        insecure: bool = False,
        auth_method: Optional[AuthMethod] = None,
        **auth_config: Any,
    ) -> Dict[str, Any]:
        """Validate repository connectivity using server-configured credentials."""
        try:
            scheme = self.infer_url_scheme(repo_url)
        except Exception as e:
            return {
                "valid": False,
                "repo_url": repo_url,
                "auth_mode": "unknown",
                "error": str(e),
                "message": f"Repository validation failed: {str(e)}",
            }

        repo_config: Dict[str, Any] = {
            "repo": repo_url,
            "type": "git",
            "insecure": insecure,
        }

        try:
            if auth_method is not None and auth_config:
                if auth_method in (AuthMethod.HTTPS_BASIC, AuthMethod.HTTPS_TOKEN):
                    repo_config["username"] = auth_config.get("username", "")
                    repo_config["password"] = auth_config.get("password") or auth_config.get("token") or ""
                elif auth_method == AuthMethod.SSH_KEY:
                    repo_config["sshPrivateKey"] = auth_config.get("ssh_private_key", "")
                    if auth_config.get("insecure_ignore_host_key"):
                        repo_config["insecureIgnoreHostKey"] = True
            else:
                creds = self._resolve_server_credentials(scheme)
                if scheme == "https":
                    if creds["username"]:
                        repo_config["username"] = creds["username"]
                    if creds["password"]:
                        repo_config["password"] = creds["password"]
                else:
                    repo_config["sshPrivateKey"] = creds["ssh_private_key"]
                    if insecure:
                        repo_config["insecureIgnoreHostKey"] = True

            try:
                response = await self.client.request(
                    "POST", "/api/v1/repositories/validate", json=repo_config
                )
                conn = (response.get("connectionState") if isinstance(response, dict) else None) or {}
                conn_status = conn.get("status") or "Successful"
            except ArgoCDOperationError as api_err:
                if "(405)" not in str(api_err):
                    raise
                if scheme == "https":
                    probe = await self._probe_https_repository(
                        repo_url=repo_url,
                        username=repo_config.get("username", ""),
                        password=repo_config.get("password", ""),
                        insecure=insecure,
                    )
                    conn_status = probe["status"]
                else:
                    enc = quote(repo_url, safe="")
                    params: Dict[str, Any] = {
                        "type": "git",
                        "sshPrivateKey": repo_config.get("sshPrivateKey", ""),
                        "insecure": str(insecure).lower(),
                    }
                    await self.client.request(
                        "POST",
                        f"/api/v1/repositories/{enc}/validate",
                        params=params,
                        json=repo_url,
                    )
                    conn_status = "Successful"

            return {
                "valid": True,
                "repo_url": repo_url,
                "auth_mode": scheme,
                "connection_status": conn_status,
                "message": f"Repository '{repo_url}' connection validated successfully.",
            }
        except Exception as e:
            return {
                "valid": False,
                "repo_url": repo_url,
                "auth_mode": scheme,
                "error": str(e),
                "message": f"Repository validation failed: {str(e)}",
            }

    async def delete_repository(self, repo_url: str) -> Dict[str, Any]:
        """Delete a registered repository from ArgoCD."""
        self._check_write_access("repository deletion")
        encoded_url = quote(repo_url, safe="")
        try:
            await self.client.request("DELETE", f"/api/v1/repositories/{encoded_url}")
            return {
                "repo_url": repo_url,
                "deleted": True,
                "message": f"Repository '{repo_url}' deleted successfully.",
            }
        except ArgoCDNotFoundError as e:
            raise ArgoCDNotFoundError(
                f"Repository '{repo_url}' not found; it may have already been deleted."
            ) from e
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to delete repository '{repo_url}': {str(e)}") from e

    # ==================== Project Management Methods ====================

    @staticmethod
    def _apply_resource_restrictions(
        spec: Dict[str, Any],
        resource_restrictions: Optional[Dict[str, Any]] = None,
        cluster_resource_whitelist: Optional[List[Dict[str, str]]] = None,
        cluster_resource_blacklist: Optional[List[Dict[str, str]]] = None,
        namespace_resource_whitelist: Optional[List[Dict[str, str]]] = None,
        namespace_resource_blacklist: Optional[List[Dict[str, str]]] = None,
        orphaned_resources_warn: Optional[bool] = None,
    ) -> None:
        """Apply optional RBAC resource restriction lists onto an AppProject spec."""
        if resource_restrictions:
            cluster_resource_whitelist = resource_restrictions.get(
                "cluster_resource_whitelist",
                resource_restrictions.get("clusterResourceWhitelist", cluster_resource_whitelist),
            )
            cluster_resource_blacklist = resource_restrictions.get(
                "cluster_resource_blacklist",
                resource_restrictions.get("clusterResourceBlacklist", cluster_resource_blacklist),
            )
            namespace_resource_whitelist = resource_restrictions.get(
                "namespace_resource_whitelist",
                resource_restrictions.get("namespaceResourceWhitelist", namespace_resource_whitelist),
            )
            namespace_resource_blacklist = resource_restrictions.get(
                "namespace_resource_blacklist",
                resource_restrictions.get("namespaceResourceBlacklist", namespace_resource_blacklist),
            )
            if "orphaned_resources_warn" in resource_restrictions or "orphanedResourcesWarn" in resource_restrictions:
                orphaned_resources_warn = bool(
                    resource_restrictions.get(
                        "orphaned_resources_warn",
                        resource_restrictions.get("orphanedResourcesWarn"),
                    )
                )

        if cluster_resource_whitelist is not None:
            spec["clusterResourceWhitelist"] = cluster_resource_whitelist
        if cluster_resource_blacklist is not None:
            spec["clusterResourceBlacklist"] = cluster_resource_blacklist
        if namespace_resource_whitelist is not None:
            spec["namespaceResourceWhitelist"] = namespace_resource_whitelist
        if namespace_resource_blacklist is not None:
            spec["namespaceResourceBlacklist"] = namespace_resource_blacklist
        if orphaned_resources_warn is not None:
            if orphaned_resources_warn:
                spec["orphanedResources"] = {"warn": True}
            else:
                spec.pop("orphanedResources", None)

    async def create_project(
        self,
        project_name: str,
        description: str,
        source_repos: List[str],
        destinations: List[Dict[str, str]],
        resource_restrictions: Optional[Dict[str, Any]] = None,
        cluster_resource_whitelist: Optional[List[Dict[str, str]]] = None,
        cluster_resource_blacklist: Optional[List[Dict[str, str]]] = None,
        namespace_resource_whitelist: Optional[List[Dict[str, str]]] = None,
        namespace_resource_blacklist: Optional[List[Dict[str, str]]] = None,
        orphaned_resources_warn: bool = False,
    ) -> Dict[str, Any]:
        """Create a new ArgoCD AppProject without leaking raw API responses."""
        self._check_write_access("project creation")

        if not project_name or not project_name.strip():
            raise ValueError("Project name cannot be empty")
        if not source_repos:
            raise ValueError("At least one source repository must be specified")
        if not destinations:
            raise ValueError("At least one destination must be specified")

        project_spec: Dict[str, Any] = {
            "sourceRepos": source_repos,
            "destinations": destinations,
        }
        self._apply_resource_restrictions(
            project_spec,
            resource_restrictions=resource_restrictions,
            cluster_resource_whitelist=cluster_resource_whitelist,
            cluster_resource_blacklist=cluster_resource_blacklist,
            namespace_resource_whitelist=namespace_resource_whitelist,
            namespace_resource_blacklist=namespace_resource_blacklist,
            orphaned_resources_warn=orphaned_resources_warn if orphaned_resources_warn else None,
        )

        project_obj: Dict[str, Any] = {
            "metadata": {"name": project_name},
            "spec": project_spec,
        }
        if description:
            project_obj["metadata"]["annotations"] = {"description": description}

        try:
            await self.client.request(
                "POST", "/api/v1/projects", json={"project": project_obj}
            )
            return {
                "project_name": project_name,
                "description": description,
                "created": True,
                "source_repos": source_repos,
                "destinations": destinations,
                "message": f"Project '{project_name}' created successfully.",
            }
        except (ArgoCDConflictError, ArgoCDOperationError) as e:
            if isinstance(e, ArgoCDConflictError) or "already exists" in str(e).lower():
                raise ArgoCDOperationError(
                    f"Project '{project_name}' already exists. "
                    "Call 'get_project' to inspect it or 'update_project' to modify it."
                ) from e
            raise ArgoCDOperationError(f"Failed to create project '{project_name}': {str(e)}") from e

    async def list_projects(
        self,
        name_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List all ArgoCD projects with concise summaries."""
        try:
            response = await self.client.request("GET", "/api/v1/projects")
            items = (response.get("items") if isinstance(response, dict) else None) or []

            if name_filter:
                items = [
                    p
                    for p in items
                    if name_filter.lower() in ((p.get("metadata") or {}).get("name") or "").lower()
                ]

            projects = []
            for proj in items:
                metadata = proj.get("metadata") or {}
                spec = proj.get("spec") or {}
                projects.append({
                    "name": metadata.get("name"),
                    "description": (
                        (metadata.get("annotations") or {}).get("description")
                        or spec.get("description")
                        or ""
                    ),
                    "source_repos": spec.get("sourceRepos") or [],
                    "destinations": spec.get("destinations") or [],
                })

            return {
                "total": len(projects),
                "projects": projects,
            }
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to list projects: {str(e)}") from e

    async def _fetch_raw_project(self, project_name: str) -> Dict[str, Any]:
        """Fetch raw project object internally for read-modify-write updates."""
        try:
            return await self.client.request("GET", f"/api/v1/projects/{project_name}")
        except ArgoCDNotFoundError as e:
            raise ArgoCDNotFoundError(
                f"Project '{project_name}' not found. "
                "Call 'list_projects' to see available projects."
            ) from e

    async def get_project(self, project_name: str) -> Dict[str, Any]:
        """Get project details without leaking raw_response."""
        try:
            response = await self._fetch_raw_project(project_name)
            metadata = response.get("metadata") or {}
            spec = response.get("spec") or {}
            return {
                "name": metadata.get("name", project_name),
                "description": (
                    (metadata.get("annotations") or {}).get("description")
                    or spec.get("description")
                    or ""
                ),
                "source_repos": spec.get("sourceRepos") or [],
                "destinations": spec.get("destinations") or [],
                "cluster_resource_whitelist": spec.get("clusterResourceWhitelist") or [],
                "cluster_resource_blacklist": spec.get("clusterResourceBlacklist") or [],
                "namespace_resource_whitelist": spec.get("namespaceResourceWhitelist") or [],
                "namespace_resource_blacklist": spec.get("namespaceResourceBlacklist") or [],
                "orphaned_resources": spec.get("orphanedResources"),
            }
        except ArgoCDNotFoundError:
            raise
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to get project '{project_name}': {str(e)}") from e

    async def update_project(
        self,
        project_name: str,
        description: Optional[str] = None,
        source_repos: Optional[List[str]] = None,
        destinations: Optional[List[Dict[str, str]]] = None,
        resource_restrictions: Optional[Dict[str, Any]] = None,
        cluster_resource_whitelist: Optional[List[Dict[str, str]]] = None,
        cluster_resource_blacklist: Optional[List[Dict[str, str]]] = None,
        namespace_resource_whitelist: Optional[List[Dict[str, str]]] = None,
        namespace_resource_blacklist: Optional[List[Dict[str, str]]] = None,
        orphaned_resources_warn: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update an existing ArgoCD project."""
        self._check_write_access("project update")

        project_data = await self._fetch_raw_project(project_name)
        metadata = project_data.setdefault("metadata", {"name": project_name})
        spec = project_data.setdefault("spec", {})

        if description is not None:
            metadata.setdefault("annotations", {})["description"] = description
        if source_repos is not None:
            spec["sourceRepos"] = source_repos
        if destinations is not None:
            spec["destinations"] = destinations

        self._apply_resource_restrictions(
            spec,
            resource_restrictions=resource_restrictions,
            cluster_resource_whitelist=cluster_resource_whitelist,
            cluster_resource_blacklist=cluster_resource_blacklist,
            namespace_resource_whitelist=namespace_resource_whitelist,
            namespace_resource_blacklist=namespace_resource_blacklist,
            orphaned_resources_warn=orphaned_resources_warn,
        )

        try:
            await self.client.request(
                "PUT", f"/api/v1/projects/{project_name}", json={"project": project_data}
            )
            return {
                "project_name": project_name,
                "updated": True,
                "source_repos": spec.get("sourceRepos") or [],
                "destinations": spec.get("destinations") or [],
                "message": f"Project '{project_name}' updated successfully.",
            }
        except ArgoCDNotFoundError:
            raise
        except Exception as e:
            raise ArgoCDOperationError(f"Failed to update project '{project_name}': {str(e)}") from e

    async def delete_project(self, project_name: str) -> Dict[str, Any]:
        """Delete an ArgoCD project, checking for active applications first."""
        self._check_write_access("project deletion")
        if project_name == "default":
            raise ArgoCDOperationError("The 'default' ArgoCD project cannot be deleted.")

        try:
            await self.client.request("DELETE", f"/api/v1/projects/{project_name}")
            return {
                "project_name": project_name,
                "deleted": True,
                "message": f"Project '{project_name}' deleted successfully.",
            }
        except ArgoCDNotFoundError as e:
            raise ArgoCDNotFoundError(
                f"Project '{project_name}' not found; it may have already been deleted."
            ) from e
        except Exception as e:
            err_str = str(e)
            if "applications" in err_str.lower() or "in use" in err_str.lower():
                raise ArgoCDOperationError(
                    f"Cannot delete project '{project_name}' because applications still belong to it. "
                    f"Call list_applications(project='{project_name}') and delete or move those applications first."
                ) from e
            raise ArgoCDOperationError(f"Failed to delete project '{project_name}': {str(e)}") from e
