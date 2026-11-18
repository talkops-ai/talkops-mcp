"""Helm chart discovery and repository management tools."""

from typing import Any, Dict, List, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from helm_mcp_server.tools.base import BaseTool


class ChartDiscoveryTools(BaseTool):
    """Tools for searching Helm chart repositories and registering repository URLs."""

    def register(self, mcp_instance: Any) -> None:
        """Register chart discovery tools with FastMCP."""

        @mcp_instance.tool(
            tags={"read"},
            annotations=ToolAnnotations(
                title="Search Helm Charts",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def helm_search_charts(
            query: str = Field(..., min_length=1, description="Chart name or keyword (e.g., 'postgresql', 'argo-cd')"),
            repository: Optional[str] = Field(
                default=None,
                description="Optional configured repository filter (e.g., 'bitnami', 'argo')",
            ),
            versions: bool = Field(
                default=False,
                description="Include all available chart versions instead of only the latest version",
            ),
            limit: int = Field(
                default=10,
                ge=1,
                le=50,
                description="Maximum number of matching charts to return (1-50)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> List[Dict[str, Any]]:
            """Search configured Helm chart repositories by keyword.

            Returns a list of matching chart summaries:
            [{"name": "<repo>/<chart>", "version": str, "app_version": str, "description": str}].
            """
            if ctx:
                await ctx.info(
                    f"Searching Helm charts matching '{query}'",
                    extra={"query": query, "repository": repository, "versions": versions, "limit": limit},
                )
            return await self.helm_service.search_charts(
                query=query,
                repository=repository,
                versions=versions,
                limit=limit,
            )

        @mcp_instance.tool(
            tags={"mutate"},
            annotations=ToolAnnotations(
                title="Ensure Helm Repository Exists",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def helm_ensure_repository(
            repo_name: str = Field(..., min_length=1, description="Repository alias (e.g., 'bitnami', 'argo')"),
            repo_url: str = Field(
                ...,
                min_length=1,
                description="Canonical HTTP/HTTPS Helm chart repository URL (e.g., 'https://charts.bitnami.com/bitnami')",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Add and index a Helm chart repository if not already configured.

            Returns {"repository": str, "added": bool, "message": str}.
            """
            if ctx:
                await ctx.info(
                    f"Ensuring Helm repository '{repo_name}' ({repo_url})",
                    extra={"repo_name": repo_name, "repo_url": repo_url},
                )
            return await self.helm_service.ensure_repository(
                repo_name=repo_name,
                repo_url=repo_url,
            )
