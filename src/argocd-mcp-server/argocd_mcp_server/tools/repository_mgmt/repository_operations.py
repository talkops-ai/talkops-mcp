"""Repository Management Tools - 5 tools for ArgoCD repository onboarding and inspection."""

from typing import Any, Dict, Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from argocd_mcp_server.tools.base import BaseTool


class RepositoryManagementTools(BaseTool):
    """Tools for managing ArgoCD repositories with server-side credential resolution."""

    toolset_name: str = "repositories"

    def register(self, mcp_instance: Any) -> None:
        """Register repository management tools with FastMCP."""

        if self.should_register_tool(is_read_only=True):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="List Repositories",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def list_repositories(
                repo_filter: Optional[str] = Field(
                    default=None,
                    description="Optional case-insensitive substring filter on repository URL.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """List all repositories registered in ArgoCD with credentials redacted."""
                await self._log_info(
                    ctx,
                    "Listing ArgoCD repositories",
                    extra={"repo_filter": repo_filter},
                )
                return await self.mgmt_service.list_repositories(repo_filter=repo_filter)

            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Get Repository",
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=True,
                )
            )
            async def get_repository(
                repo_url: str = Field(
                    ...,
                    description="Full repository URL (https://..., ssh://..., or git@...).",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Get repository connection status and metadata (credentials redacted)."""
                await self._log_info(
                    ctx,
                    f"Getting repository details for {repo_url}",
                    extra={"repo_url": repo_url},
                )
                return await self.mgmt_service.get_repository(repo_url=repo_url)

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
                repo_url: str = Field(
                    ...,
                    description="Repository URL to validate (https://..., ssh://..., or git@...).",
                ),
                insecure: bool = Field(
                    default=False,
                    description="If True, skip TLS certificate or SSH host key verification during validation.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Validate repository connectivity using server-configured Git credentials."""
                await self._log_info(
                    ctx,
                    f"Validating repository connection for {repo_url}",
                    extra={"repo_url": repo_url, "insecure": insecure},
                )
                return await self.mgmt_service.validate_repository_connection(
                    repo_url=repo_url,
                    insecure=insecure,
                )

        if self.should_register_tool(is_read_only=False):
            @mcp_instance.tool(
                annotations=ToolAnnotations(
                    title="Onboard Repository",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def onboard_repository(
                repo_url: str = Field(
                    ...,
                    description="Repository URL (https://... for HTTPS, ssh://... or git@... for SSH).",
                ),
                repo_type: Literal["git", "helm", "oci"] = Field(
                    default="git",
                    description="Repository type: 'git', 'helm', or 'oci'.",
                ),
                project: Optional[str] = Field(
                    default=None,
                    description="Optional ArgoCD AppProject name to scope this repository to.",
                ),
                enable_lfs: bool = Field(
                    default=False,
                    description="If True, enable Git LFS support for the repository.",
                ),
                insecure: bool = Field(
                    default=False,
                    description="If True, skip TLS verification (HTTPS) or host key verification (SSH).",
                ),
                force_http_basic_auth: bool = Field(
                    default=False,
                    description="If True, force HTTP basic auth header for HTTPS repositories.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Onboard a Git/Helm/OCI repository into ArgoCD using server-side credentials (inferred from URL scheme)."""
                await self._log_info(
                    ctx,
                    f"Onboarding repository {repo_url}",
                    extra={"repo_url": repo_url, "repo_type": repo_type, "project": project},
                )
                return await self.mgmt_service.onboard_repository(
                    repo_url=repo_url,
                    repo_type=repo_type,
                    project=project,
                    enable_lfs=enable_lfs,
                    insecure=insecure,
                    force_http_basic_auth=force_http_basic_auth,
                )

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
                repo_url: str = Field(
                    ...,
                    description="URL of the repository to remove from ArgoCD.",
                ),
                confirm: bool = Field(
                    default=False,
                    description="Set True after operator confirmation to execute deletion.",
                ),
                ctx: Optional[Context] = None,
            ) -> Dict[str, Any]:
                """Delete a registered repository from ArgoCD."""
                self.mgmt_service._check_write_access("repository deletion")
                gate = await self.confirm_destructive_action(
                    ctx,
                    f"delete repository '{repo_url}'",
                    confirm=confirm,
                    impact_preview={
                        "operation": "delete_repository",
                        "repo_url": repo_url,
                        "effect": "Removes repository credentials and configuration from ArgoCD; applications using this repo will fail to sync.",
                    },
                )
                if gate is not None:
                    return gate

                await self._log_warning(
                    ctx,
                    f"Deleting repository {repo_url}",
                    extra={"repo_url": repo_url},
                )
                return await self.mgmt_service.delete_repository(repo_url=repo_url)
