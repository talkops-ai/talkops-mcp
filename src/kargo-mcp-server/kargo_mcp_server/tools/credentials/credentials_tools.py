"""Kargo credentials tools."""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError, KargoValidationError
from kargo_mcp_server.tools.base import BaseTool
from kargo_mcp_server.models.credentials import CreateRepoCredentialsRequest


class CredentialsTools(BaseTool):
    """Tools for managing Kargo repository credentials."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_credentials_mgmt(
            action: Literal["list", "get", "create", "delete"],
            project: str = Field(..., min_length=1, description="Kargo project name"),
            name: Optional[str] = Field(None, description="Credential name (required for get, delete, create)"),
            repo_url: Optional[str] = Field(None, description="Repository URL (required for create)"),
            type: Optional[str] = Field(None, description="Credential type e.g., git, helm, image (required for create)"),
            username: Optional[str] = Field(None, description="Username for the repository"),
            password: Optional[str] = Field(None, description="Password/token for the repository"),
            description: Optional[str] = Field(None, description="Description of the credential"),
            repo_url_is_regex: Optional[bool] = Field(False, description="Whether the repo URL is a regex pattern"),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Manage Kargo Repository Credentials.

            Use this tool to list, retrieve, create, or delete Kargo repository credentials.
            These credentials authenticate Kargo to external Git repositories or Container registries.

            Actions:
            - list: Discover all repository credentials in a project.
            - get: Retrieve configuration details for a specific repository credential.
            - create: Create new repository credentials (requires allow_write=true).
            - delete: Delete repository credentials (requires allow_write=true).

            Args:
                action: Operation to perform (list, get, create, delete)
                project: Name of the Kargo project
                name: Name of the credential (required for get, delete, create)
                repo_url: Repository URL (required for create)
                type: Credential type, e.g., "git", "helm", "image" (required for create)
                username: Optional username (falls back to KARGO_REPO_USERNAME env var)
                password: Optional password/token (falls back to KARGO_REPO_PASSWORD env var)
                description: Optional description
                repo_url_is_regex: Whether repo_url is a regex

            Returns:
                Depends on the action requested.
            """
            if action in ["create", "delete"] and not self.config.allow_write:
                raise KargoOperationError(
                    "Write operations are disabled. Set MCP_ALLOW_WRITE=true to enable."
                )

            if action in ["get", "delete", "create"] and not name:
                raise KargoValidationError(f"'name' is required for action '{action}'")

            if action == "list":
                await ctx.info(
                    f"Listing repository credentials for project '{project}'",
                    extra={'project': project}
                )
                try:
                    creds = await self.kargo_service.list_repo_credentials(project)
                    await ctx.info(
                        f"Found {len(creds)} repository credentials",
                        extra={'project': project, 'count': len(creds)}
                    )
                    if not creds:
                        return [{"message": f"No repository credentials found in project '{project}'."}]
                    return creds
                except Exception as e:
                    friendly_msg = (
                        f"Failed to list credentials: {str(e)}. "
                        "Verify the project exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "get":
                if not isinstance(name, str):
                    raise KargoValidationError("name must be a string")
                await ctx.info(
                    f"Fetching repository credentials '{name}' in project '{project}'",
                    extra={'project': project, 'cred_name': name}
                )
                try:
                    cred = await self.kargo_service.get_repo_credentials(project, name)
                    await ctx.info(f"Successfully retrieved credentials '{name}'")
                    return cred
                except Exception as e:
                    friendly_msg = (
                        f"Failed to get credentials '{name}': {str(e)}. "
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "delete":
                if not isinstance(name, str):
                    raise KargoValidationError("name must be a string")
                await ctx.info(
                    f"Deleting repository credentials '{name}' in project '{project}'",
                    extra={'project': project, 'cred_name': name}
                )
                try:
                    res = await self.kargo_service.delete_repo_credentials(project, name)
                    await ctx.info(f"Successfully deleted credentials '{name}'")
                    return res
                except Exception as e:
                    friendly_msg = (
                        f"Failed to delete credentials '{name}': {str(e)}. "
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "create":
                if not isinstance(name, str):
                    raise KargoValidationError("name must be a string")
                if not repo_url:
                    raise KargoValidationError("'repo_url' is required for action 'create'")
                if not type:
                    raise KargoValidationError("'type' is required for action 'create'")

                # Resolve credentials: tool params take precedence, then env vars.
                # This keeps secrets out of agent conversations while still
                # allowing explicit overrides when needed.
                resolved_username = username or self.config.kargo.repo_username
                resolved_password = password or self.config.kargo.repo_password

                if not resolved_username or not resolved_password:
                    missing = []
                    if not resolved_username:
                        missing.append("username (set KARGO_REPO_USERNAME env var)")
                    if not resolved_password:
                        missing.append("password (set KARGO_REPO_PASSWORD env var)")
                    await ctx.warning(
                        f"Missing credentials: {', '.join(missing)}. "
                        "The credential will be created without authentication."
                    )

                await ctx.info(
                    f"Creating repository credentials '{name}' in project '{project}'",
                    extra={'project': project, 'cred_name': name}
                )
                try:
                    req = CreateRepoCredentialsRequest(
                        name=name,
                        repoUrl=repo_url,
                        type=type,
                        username=resolved_username,
                        password=resolved_password,
                        description=description,
                        repoUrlIsRegex=repo_url_is_regex,
                    )
                    cred = await self.kargo_service.create_repo_credentials(project, req)
                    msg = f"Successfully created repository credentials '{name}'"
                    if resolved_username:
                        msg += f" (username: {resolved_username[:3]}***)"
                    await ctx.info(msg)
                    return cred
                except Exception as e:
                    friendly_msg = (
                        f"Failed to create credentials '{name}': {str(e)}. "
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)
            
            return {}
