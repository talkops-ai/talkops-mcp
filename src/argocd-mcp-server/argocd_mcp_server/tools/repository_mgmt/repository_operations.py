"""Repository management and onboarding tools."""

import os
from typing import Dict, Any, Optional
from pydantic import Field
from mcp.types import ToolAnnotations
from fastmcp import Context

from argocd_mcp_server.tools.base import BaseTool
from argocd_mcp_server.services.argocd_mgmt import (
    ArgoCDManagementService,
    RepositoryType,
    AuthMethod
)
from argocd_mcp_server.exceptions import (
    ArgoCDOperationError,
    ArgoCDNotFoundError,
    ArgoCDConnectionError
)


class RepositoryManagementTools(BaseTool):
    """Tools for managing and onboarding Git repositories into ArgoCD."""
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator."""
        super().__init__(service_locator)
        # Create management service instance
        self.mgmt_service = ArgoCDManagementService(self.config)
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Onboard Repository via HTTPS",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def onboard_repository_https(
            repo_url: str = Field(..., min_length=1, description='Repository URL (must start with https://)'),
            repo_type: str = Field(default="git", description='Repository type: git, helm, or oci'),
            enable_lfs: bool = Field(default=False, description='Enable Git LFS support'),
            project: Optional[str] = Field(default=None, description='Project-scoped repository'),
            insecure: bool = Field(default=False, description='Skip TLS certificate verification'),
            force_http_basic_auth: bool = Field(default=False, description='Force HTTP basic authentication'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Onboard a Git repository using HTTPS authentication.

            Registers a new repository with ArgoCD using username/password
            or token-based authentication over HTTPS.

            🔒 SECURITY: Credentials are read from environment variables
            (GIT_USERNAME / GIT_PASSWORD) to prevent exposure to the LLM.

            Returns:
            - {"summary": str, "connection_state": {"status": str}, ...}

            When NOT to use:
            - For SSH authentication → use onboard_repository_ssh.
            - To test connection first → use validate_repository_connection.

            Common errors:
            - Repository already exists: Use get_repository to view it.
            - Authentication failed: Check GIT_PASSWORD env var.
            """
            await ctx.info(
                f"Onboarding HTTPS repository: {repo_url}",
                extra={'repo_url': repo_url, 'repo_type': repo_type}
            )
            
            # Validate repo_url format
            if not repo_url.startswith('https://'):
                error_msg = "HTTPS repository URL must start with 'https://'. For SSH repositories, use 'onboard_repository_ssh'."
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            # Credentials from config (loaded from GIT_USERNAME / GIT_PASSWORD in config.py)
            username = self.config.git.username
            password = self.config.git.password
            if not password:
                error_msg = (
                    "Git HTTPS credentials not set. Set GIT_PASSWORD (and optionally GIT_USERNAME) "
                    "in the environment; they are loaded via config (see argocd_mcp_server.config.GitRepoConfig).\n"
                    "  export GIT_PASSWORD='your-token-here'"
                )
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            await ctx.info("✓ Using Git credentials from config (GIT_USERNAME / GIT_PASSWORD)")
            
            # Convert repo_type string to enum
            try:
                repo_type_enum = RepositoryType(repo_type.lower())
            except ValueError:
                error_msg = f"Invalid repo_type '{repo_type}'. Must be one of: git, helm, oci"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            try:
                result = await self.mgmt_service.onboard_repository_https(
                    repo_url=repo_url,
                    username=username,
                    password=password,
                    repo_type=repo_type_enum,
                    enable_lfs=enable_lfs,
                    project=project,
                    insecure=insecure,
                    force_http_basic_auth=force_http_basic_auth
                )
                
                await ctx.info(
                    f"Successfully onboarded repository: {repo_url}",
                    extra={'connection_state': result.get('connection_state')}
                )
                
                # Create human-readable summary
                connection_state = result.get('connection_state', {})
                status = connection_state.get('status', 'Unknown')
                
                summary = (
                    f"Repository '{repo_url}' onboarded successfully via HTTPS. "
                    f"Connection status: {status}. "
                    f"You can now create ArgoCD applications using this repository."
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDOperationError as e:
                error_msg = str(e)
                if "already exists" in error_msg.lower():
                    friendly_msg = (
                        f"Repository '{repo_url}' is already registered in ArgoCD. "
                        f"Use 'get_repository' to view its configuration or 'list_repositories' to see all registered repositories."
                    )
                    await ctx.warning(friendly_msg)
                    raise ArgoCDOperationError(friendly_msg)
                else:
                    friendly_msg = (
                        f"Failed to onboard HTTPS repository '{repo_url}': {error_msg}. "
                        f"Verify the URL, credentials, and network connectivity. "
                        f"Use 'validate_repository_connection' to test the connection before onboarding."
                    )
                    await ctx.error(friendly_msg)
                    raise ArgoCDOperationError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Unexpected error while onboarding repository: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Onboard Repository via SSH",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def onboard_repository_ssh(
            repo_url: str = Field(..., min_length=1, description='SSH repository URL (ssh://git@... or git@...)'),
            repo_type: str = Field(default="git", description='Repository type: git, helm, or oci'),
            enable_lfs: bool = Field(default=False, description='Enable Git LFS support'),
            project: Optional[str] = Field(default=None, description='Project-scoped repository'),
            insecure_ignore_host_key: bool = Field(default=False, description='Skip SSH host key verification'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Onboard a Git repository using SSH key authentication.

            Registers a new repository with ArgoCD using SSH deploy keys
            or user SSH keys.

            🔒 SECURITY: SSH private key is read from a file path
            (SSH_PRIVATE_KEY_PATH env var, default: ~/.ssh/id_rsa)
            to prevent exposure to the LLM.

            Returns:
            - {"summary": str, "connection_state": {"status": str}, ...}

            When NOT to use:
            - For HTTPS/token auth → use onboard_repository_https.
            - To test connection first → use validate_repository_connection.

            Common errors:
            - Repository already exists: Use get_repository to view it.
            - SSH key not found: Check SSH_PRIVATE_KEY_PATH env var.
            - Host key verification failed: Set insecure_ignore_host_key=True.
            """
            await ctx.info(
                f"Onboarding SSH repository: {repo_url}",
                extra={'repo_url': repo_url, 'repo_type': repo_type}
            )
            
            # Validate repo_url format
            if not (repo_url.startswith('ssh://') or repo_url.startswith('git@')):
                error_msg = "SSH repository URL must start with 'ssh://' or 'git@'. For HTTPS repositories, use 'onboard_repository_https'."
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            # SSH key path from config (loaded from SSH_PRIVATE_KEY_PATH in config.py)
            ssh_key_path = os.path.expanduser(self.config.git.ssh_private_key_path)
            await ctx.info(f"Using SSH key path from config (SSH_PRIVATE_KEY_PATH): {ssh_key_path}")
            
            # Check if file exists
            if not os.path.exists(ssh_key_path):
                error_msg = f"SSH private key file not found at path: {ssh_key_path}"
                await ctx.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # Read the SSH private key from file
            try:
                with open(ssh_key_path, 'r') as key_file:
                    ssh_private_key = key_file.read()
            except Exception as read_error:
                error_msg = f"Failed to read SSH private key from {ssh_key_path}: {str(read_error)}"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            # Validate SSH key format
            if not ssh_private_key.strip():
                error_msg = "SSH private key file is empty"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            if "BEGIN" not in ssh_private_key or "PRIVATE KEY" not in ssh_private_key:
                await ctx.warning(
                    "SSH private key does not appear to contain standard BEGIN/END headers. "
                    "Ensure the key is in proper PEM format."
                )
            
            await ctx.info(f"✓ SSH private key loaded from {ssh_key_path}")
            
            # Convert repo_type string to enum
            try:
                repo_type_enum = RepositoryType(repo_type.lower())
            except ValueError:
                error_msg = f"Invalid repo_type '{repo_type}'. Must be one of: git, helm, oci"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            try:
                result = await self.mgmt_service.onboard_repository_ssh(
                    repo_url=repo_url,
                    ssh_private_key=ssh_private_key,
                    repo_type=repo_type_enum,
                    enable_lfs=enable_lfs,
                    project=project,
                    insecure_ignore_host_key=insecure_ignore_host_key
                )
                
                await ctx.info(
                    f"Successfully onboarded repository: {repo_url}",
                    extra={'connection_state': result.get('connection_state')}
                )
                
                # Create human-readable summary
                connection_state = result.get('connection_state', {})
                status = connection_state.get('status', 'Unknown')
                
                summary = (
                    f"Repository '{repo_url}' onboarded successfully via SSH. "
                    f"Connection status: {status}. "
                    f"You can now create ArgoCD applications using this repository."
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDOperationError as e:
                error_msg = str(e)
                if "already exists" in error_msg.lower():
                    friendly_msg = (
                        f"Repository '{repo_url}' is already registered in ArgoCD. "
                        f"Use 'get_repository' to view its configuration or 'list_repositories' to see all registered repositories."
                    )
                    await ctx.warning(friendly_msg)
                    raise ArgoCDOperationError(friendly_msg)
                else:
                    friendly_msg = (
                        f"Failed to onboard SSH repository '{repo_url}': {error_msg}. "
                        f"Common issues: invalid SSH key format, incorrect permissions, or SSH host key mismatch. "
                        f"Use 'validate_repository_connection' to test the connection before onboarding."
                    )
                    await ctx.error(friendly_msg)
                    raise ArgoCDOperationError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Unexpected error while onboarding repository: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List ArgoCD Repositories",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def list_repositories(
            repo_filter: Optional[str] = Field(default=None, description='Optional URL filter to search repositories'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List all Git repositories registered in ArgoCD.

            Use to discover available repositories before creating
            applications. Optionally filter by URL. Read-only.

            Returns:
            - {"summary": str, "total": int,
               "repositories": [{"url": str, "type": str, ...}]}

            When NOT to use:
            - To get details of one repo → use get_repository.
            - To register a new repo → use onboard_repository_https.
            """
            await ctx.info(
                "Listing ArgoCD repositories",
                extra={'filter': repo_filter or 'none'}
            )
            
            try:
                result = await self.mgmt_service.list_repositories(
                    repo_filter=repo_filter
                )
                
                total = result.get('total', 0)
                await ctx.info(
                    f"Found {total} registered repositories",
                    extra={'total': total}
                )
                
                if total == 0:
                    summary = (
                        "No repositories registered in ArgoCD. "
                        "Use 'onboard_repository_https' or 'onboard_repository_ssh' to register a new repository."
                    )
                else:
                    summary = f"Found {total} registered repositories in ArgoCD."
                
                return {
                    "summary": summary,
                    **result
                }
                
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to list repositories: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Repository Details",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def get_repository(
            repo_url: str = Field(..., min_length=1, description='Repository URL (must match exactly as registered)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get detailed information about a specific registered repository.

            Use to check connection state, authentication method, and
            configuration for a repository. Read-only.

            Returns:
            - {"summary": str, "url": str, "type": str,
               "connection_state": {"status": str}, ...}

            When NOT to use:
            - To list all repos → use list_repositories.
            - To test connectivity → use validate_repository_connection.
            """
            await ctx.info(
                f"Getting repository details: {repo_url}",
                extra={'repo_url': repo_url}
            )
            
            try:
                result = await self.mgmt_service.get_repository(repo_url=repo_url)
                
                connection_state = result.get('connection_state', {})
                status = connection_state.get('status', 'Unknown')
                
                await ctx.info(
                    f"Repository found: {repo_url}",
                    extra={'status': status}
                )
                
                summary = f"Repository '{repo_url}' - Connection status: {status}"
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDNotFoundError:
                friendly_msg = (
                    f"Repository '{repo_url}' not found in ArgoCD. "
                    f"Use 'list_repositories' to see all registered repositories, or "
                    f"use 'onboard_repository_https' / 'onboard_repository_ssh' to register it."
                )
                await ctx.error(friendly_msg)
                raise ArgoCDNotFoundError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to get repository details: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate Repository Connection",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def validate_repository_connection(
            repo_url: str = Field(..., min_length=1, description='Repository URL to validate'),
            auth_method: str = Field(..., description='Authentication method: https_basic, https_token, or ssh_key'),
            username: Optional[str] = Field(default=None, description='Username for HTTPS auth'),
            password: Optional[str] = Field(default=None, description='Password/token for HTTPS auth'),
            ssh_private_key: Optional[str] = Field(default=None, description='SSH private key for SSH auth'),
            insecure: bool = Field(default=False, description='Skip TLS/SSH host verification'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Validate repository connection without onboarding.

            Use to test connectivity and authentication before registering
            a repository with ArgoCD. Read-only — does not register
            the repository.

            Returns:
            - {"summary": str, "valid": bool, "error": str | null}

            When NOT to use:
            - To onboard the repo → use onboard_repository_https or onboard_repository_ssh.
            """
            await ctx.info(
                f"Validating repository connection: {repo_url}",
                extra={'repo_url': repo_url, 'auth_method': auth_method}
            )
            
            # Convert auth_method string to enum
            try:
                auth_method_enum = AuthMethod(auth_method.lower())
            except ValueError:
                error_msg = (
                    f"Invalid auth_method '{auth_method}'. "
                    f"Must be one of: https_basic, https_token, ssh_key"
                )
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            # Build auth config
            auth_config = {"insecure": insecure}
            
            if auth_method_enum in [AuthMethod.HTTPS_BASIC, AuthMethod.HTTPS_TOKEN]:
                if not password:
                    password = self.config.git.password
                    if password:
                        await ctx.info("Using Git password/token from environment configuration")
                if not password:
                    error_msg = "Password/token is required for HTTPS authentication"
                    await ctx.error(error_msg)
                    raise ValueError(error_msg)
                
                if not username:
                    username = self.config.git.username
                auth_config["username"] = username or ""
                auth_config["password"] = password
            elif auth_method_enum == AuthMethod.SSH_KEY:
                # If key not provided, read from config path (SSH_PRIVATE_KEY_PATH)
                if not ssh_private_key:
                    ssh_key_path = os.path.expanduser(self.config.git.ssh_private_key_path)
                    if os.path.exists(ssh_key_path):
                        await ctx.info(f"Reading SSH key from config path: {ssh_key_path}")
                        try:
                            with open(ssh_key_path, 'r') as key_file:
                                ssh_private_key = key_file.read()
                        except Exception as e:
                            await ctx.warning(f"Failed to read SSH key from {ssh_key_path}: {e}")

                if not ssh_private_key:
                    error_msg = "SSH private key is required for SSH authentication"
                    await ctx.error(error_msg)
                    raise ValueError(error_msg)
                auth_config["ssh_private_key"] = ssh_private_key
                if insecure:
                    auth_config["insecure_ignore_host_key"] = True
            
            try:
                result = await self.mgmt_service.validate_repository_connection(
                    repo_url=repo_url,
                    auth_method=auth_method_enum,
                    **auth_config
                )
                
                is_valid = result.get('valid', False)
                
                if is_valid:
                    await ctx.info(f"Repository connection validated successfully: {repo_url}")
                    summary = f"Repository '{repo_url}' is accessible and authentication is valid. Ready for onboarding."
                else:
                    await ctx.warning(f"Repository connection validation failed: {repo_url}")
                    summary = f"Repository '{repo_url}' validation failed: {result.get('error', 'Unknown error')}"
                
                return {
                    "summary": summary,
                    **result
                }
                
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to validate repository connection: {error_msg}"
                await ctx.error(friendly_msg)
                # Return validation failure instead of raising
                return {
                    "valid": False,
                    "repo_url": repo_url,
                    "error": error_msg,
                    "summary": f"Repository validation failed: {error_msg}"
                }
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Repository",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def delete_repository(
            repo_url: str = Field(..., min_length=1, description='Repository URL to delete (must match exactly)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Delete a repository registration from ArgoCD.

            Use when removing a repository's credentials from ArgoCD.

            **WARNING: This does NOT delete applications using this
            repository — they will fail to sync until the repository
            is re-registered.**

            Returns:
            - {"summary": str, "status": str}

            When NOT to use:
            - To delete an application → use delete_application.
            """
            await ctx.warning(
                f"Deleting repository: {repo_url}",
                extra={'repo_url': repo_url}
            )
            
            try:
                result = await self.mgmt_service.delete_repository(repo_url=repo_url)
                
                await ctx.info(f"Repository deleted successfully: {repo_url}")
                
                summary = (
                    f"Repository '{repo_url}' has been deleted from ArgoCD. "
                    f"Applications using this repository may no longer sync until the repository is re-registered."
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except ArgoCDNotFoundError:
                friendly_msg = (
                    f"Repository '{repo_url}' not found in ArgoCD. "
                    f"It may have already been deleted or never existed. No action needed."
                )
                await ctx.warning(friendly_msg)
                raise ArgoCDNotFoundError(friendly_msg)
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to delete repository: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Generate Repository Secret Manifest",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def generate_repository_secret_manifest(
            repo_url: str = Field(..., min_length=1, description='Repository URL'),
            auth_method: str = Field(..., description='Authentication method: https_basic, https_token, or ssh_key'),
            username: Optional[str] = Field(default=None, description='Username for HTTPS auth'),
            password: Optional[str] = Field(default=None, description='Password/token for HTTPS auth'),
            ssh_private_key: Optional[str] = Field(default=None, description='SSH private key for SSH auth'),
            secret_name: Optional[str] = Field(default=None, description='Kubernetes secret name (auto-generated if not provided)'),
            namespace: str = Field(default="argocd", description='Kubernetes namespace (default: argocd)'),
            repo_type: str = Field(default="git", description='Repository type: git, helm, or oci'),
            enable_lfs: bool = Field(default=False, description='Enable Git LFS support'),
            project: Optional[str] = Field(default=None, description='Project-scoped repository'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate a Kubernetes Secret manifest for declarative repository setup.

            Generates a YAML manifest that can be applied via kubectl or
            committed to Git for GitOps-managed repository registration.
            Read-only — does not apply anything to the cluster.

            Returns:
            - {"summary": str, "secret_name": str, "manifest": str}

            When NOT to use:
            - To register via API → use onboard_repository_https or onboard_repository_ssh.
            """
            await ctx.info(
                f"Generating Kubernetes Secret manifest for repository: {repo_url}",
                extra={'repo_url': repo_url, 'auth_method': auth_method, 'namespace': namespace}
            )
            
            # Convert auth_method string to enum
            try:
                auth_method_enum = AuthMethod(auth_method.lower())
            except ValueError:
                error_msg = (
                    f"Invalid auth_method '{auth_method}'. "
                    f"Must be one of: https_basic, https_token, ssh_key"
                )
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            # Convert repo_type string to enum
            try:
                repo_type_enum = RepositoryType(repo_type.lower())
            except ValueError:
                error_msg = f"Invalid repo_type '{repo_type}'. Must be one of: git, helm, oci"
                await ctx.error(error_msg)
                raise ValueError(error_msg)
            
            # Build auth config
            auth_config = {}
            
            if auth_method_enum in [AuthMethod.HTTPS_BASIC, AuthMethod.HTTPS_TOKEN]:
                if not password:
                    error_msg = "Password/token is required for HTTPS authentication"
                    await ctx.error(error_msg)
                    raise ValueError(error_msg)
                auth_config["username"] = username or ""
                auth_config["password"] = password
            elif auth_method_enum == AuthMethod.SSH_KEY:
                # If key not provided, read from config path (SSH_PRIVATE_KEY_PATH)
                if not ssh_private_key:
                    ssh_key_path = os.path.expanduser(self.config.git.ssh_private_key_path)
                    if os.path.exists(ssh_key_path):
                        await ctx.info(f"Reading SSH key from config path: {ssh_key_path}")
                        try:
                            with open(ssh_key_path, 'r') as key_file:
                                ssh_private_key = key_file.read()
                        except Exception as e:
                            await ctx.warning(f"Failed to read SSH key from {ssh_key_path}: {e}")

                if not ssh_private_key:
                    error_msg = "SSH private key is required for SSH authentication"
                    await ctx.error(error_msg)
                    raise ValueError(error_msg)
                auth_config["ssh_private_key"] = ssh_private_key
            
            try:
                result = await self.mgmt_service.generate_repository_secret_manifest(
                    repo_url=repo_url,
                    auth_method=auth_method_enum,
                    secret_name=secret_name,
                    namespace=namespace,
                    repo_type=repo_type_enum,
                    enable_lfs=enable_lfs,
                    project=project,
                    **auth_config
                )
                
                secret_name_generated = result.get('secret_name')
                await ctx.info(
                    f"Generated Kubernetes Secret manifest: {secret_name_generated}",
                    extra={'secret_name': secret_name_generated, 'namespace': namespace}
                )
                
                summary = (
                    f"Generated Kubernetes Secret manifest '{secret_name_generated}' in namespace '{namespace}'. "
                    f"Apply this manifest with: kubectl apply -f <manifest-file>.yaml"
                )
                
                return {
                    "summary": summary,
                    **result
                }
                
            except Exception as e:
                error_msg = str(e)
                friendly_msg = f"Failed to generate repository secret manifest: {error_msg}"
                await ctx.error(friendly_msg)
                raise ArgoCDOperationError(friendly_msg)
