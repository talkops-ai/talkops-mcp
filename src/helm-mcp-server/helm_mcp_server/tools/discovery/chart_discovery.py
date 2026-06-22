"""Helm chart discovery tools."""

from typing import Dict, Any, List, Optional, Union
from pydantic import Field
from mcp.types import ToolAnnotations
from fastmcp import Context
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.tools.base import BaseTool


class ChartDiscoveryTools(BaseTool):
    """Tools for discovering Helm charts."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Search Helm Charts",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def helm_search_charts(
            query: str = Field(..., description='Chart name or keyword (e.g., "postgresql", "redis", "nginx")'),
            repository: str = Field(default='bitnami', description='Helm repository name (e.g., "bitnami", "prometheus-community")'),
            limit: int = Field(default=10, ge=1, le=50, description='Maximum number of results to return'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Union[List[Dict], str]:
            """Search for Helm charts in a repository.

            Use when looking for charts to install. Returns matching
            chart metadata including versions and descriptions.
            Read-only — does not modify any state.

            Returns:
            - List of chart metadata dicts: [{"name": str, "version": str,
              "app_version": str, "description": str}, ...]
            - Or a message string if no charts are found.

            When NOT to use:
            - To get detailed info about a specific chart → use helm_get_chart_info.
            - To install a chart → use helm_install_chart.
            """
            await ctx.info(
                f"Searching for Helm charts matching '{query}'",
                extra={
                    'query': query,
                    'repository': repository,
                    'limit': limit
                }
            )
            
            await ctx.debug(f"Querying repository: {repository}")
            
            try:
                # Ensure repository exists (will be added automatically if not present)
                await ctx.debug(f"Ensuring repository '{repository}' is available")
                try:
                    await self.helm_service.ensure_repository(repository)
                    await ctx.info(
                        f"Repository '{repository}' is ready",
                        extra={'repository': repository}
                    )
                except Exception as repo_error:
                    await ctx.warning(
                        f"Could not ensure repository '{repository}': {str(repo_error)}. Proceeding with search anyway.",
                        extra={'repository': repository, 'error': str(repo_error)}
                    )
                
                # Call service with individual parameters (no serialization needed)
                charts = await self.helm_service.search_charts(
                    query=query,
                    repository=repository,
                    limit=limit
                )
                
                # Check if charts is a string (no charts found message)
                if isinstance(charts, str):
                    await ctx.warning(charts)
                    return charts
                
                await ctx.info(
                    f"Found {len(charts)} charts matching '{query}'",
                    extra={
                        'query': query,
                        'count': len(charts),
                        'repository': repository
                    }
                )
                
                return charts
            
            except Exception as e:
                await ctx.error(
                    f"Search failed: {str(e)}",
                    extra={
                        'query': query,
                        'repository': repository,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Search failed: {str(e)}')
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Helm Chart Info",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def helm_get_chart_info(
            chart_name: str = Field(..., description='Chart name (e.g., "postgresql", "nginx")'),
            repository: str = Field(default='bitnami', description='Helm repository name'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict:
            """Get detailed information about a specific Helm chart.

            Use to view chart metadata (version, description, maintainers,
            etc.) before installation. Read-only.

            Returns:
            - {"name": str, "version": str, "app_version": str,
               "description": str, "home": str, "sources": [str],
               "maintainers": [...]}

            When NOT to use:
            - To search for charts → use helm_search_charts.
            - To see default values → use helm_get_chart_values_schema.
            """
            await ctx.info(
                f"Fetching chart information for '{chart_name}'",
                extra={
                    'chart_name': chart_name,
                    'repository': repository
                }
            )
            
            await ctx.debug(f"Querying repository: {repository}")
            
            try:
                # Ensure repository exists (will be added automatically if not present)
                await ctx.debug(f"Ensuring repository '{repository}' is available")
                try:
                    await self.helm_service.ensure_repository(repository)
                    await ctx.info(
                        f"Repository '{repository}' is ready",
                        extra={'repository': repository}
                    )
                except Exception as repo_error:
                    await ctx.warning(
                        f"Could not ensure repository '{repository}': {str(repo_error)}. Proceeding anyway.",
                        extra={'repository': repository, 'error': str(repo_error)}
                    )
                
                chart_info = await self.helm_service.get_chart_info(
                    chart_name=chart_name,
                    repository=repository
                )
                
                await ctx.info(
                    f"Successfully retrieved chart info for '{chart_name}'",
                    extra={
                        'chart_name': chart_name,
                        'version': chart_info.get('version', 'unknown'),
                        'repository': repository
                    }
                )
                
                return chart_info
            
            except Exception as e:
                await ctx.error(
                    f"Failed to get chart info: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'repository': repository,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Failed to get chart info: {str(e)}')

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Helm Chart Values Schema",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def helm_get_chart_values_schema(
            chart_name: str = Field(..., description='Chart name (e.g., "postgresql", "redis")'),
            repository: str = Field(default='bitnami', description='Helm repository name'),
            version: Optional[str] = Field(default=None, description='Specific chart version (e.g., "15.5.0")'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict:
            """Get the default values (acting as schema) for a Helm chart.

            Use to understand what configuration options a chart supports
            before installation. Read-only.

            Returns:
            - Dictionary of default chart values (the values.yaml content).

            When NOT to use:
            - To get chart metadata → use helm_get_chart_info.
            - To validate your values → use helm_validate_values.
            """
            await ctx.info(
                f"Fetching values schema for '{chart_name}'",
                extra={
                    'chart_name': chart_name,
                    'repository': repository,
                    'version': version
                }
            )
            
            try:
                values = await self.helm_service.get_chart_values(
                    chart_name=chart_name,
                    repository=repository,
                    version=version
                )
                
                await ctx.info(
                    f"Successfully retrieved values schema for '{chart_name}'",
                    extra={
                        'chart_name': chart_name,
                        'repository': repository,
                        'keys_count': len(values) if values else 0
                    }
                )
                
                return values
            
            except Exception as e:
                await ctx.error(
                    f"Failed to get values schema: {str(e)}",
                    extra={
                        'chart_name': chart_name,
                        'repository': repository,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Failed to get values schema: {str(e)}')
        
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Ensure Helm Repository Exists",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def helm_ensure_repository(
            repo_name: str = Field(..., description='Repository name (e.g., "bitnami", "prometheus-community")'),
            repo_url: Optional[str] = Field(default=None, description='Repository URL (auto-detected for known repos: bitnami, argo, prometheus-community, grafana, ingress-nginx, jetstack)'),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Ensure a Helm repository exists, adding it if necessary.

            Use before helm_search_charts or helm_install_chart if the
            repository might not be configured. Idempotent — safe to call
            repeatedly. Auto-detects URLs for common repositories.

            Returns:
            - {"repository": str, "added": bool, "message": str}

            When NOT to use:
            - To search charts → use helm_search_charts (it auto-ensures repos).
            """
            await ctx.info(
                f"Ensuring Helm repository '{repo_name}' is available",
                extra={
                    'repo_name': repo_name,
                    'has_url': repo_url is not None
                }
            )
            
            await ctx.debug(f"Checking if repository '{repo_name}' exists")
            
            try:
                # Check if repository already exists
                exists = await self.helm_service.repository_exists(repo_name)
                
                if exists:
                    await ctx.info(
                        f"Repository '{repo_name}' already exists",
                        extra={'repo_name': repo_name}
                    )
                    return {
                        'repository': repo_name,
                        'added': False,
                        'message': f"Repository '{repo_name}' already exists"
                    }
                
                # Repository doesn't exist, need to add it
                await ctx.debug(f"Repository '{repo_name}' not found, adding it")
                
                # Call ensure_repository which will add it
                result_repo_name = await self.helm_service.ensure_repository(
                    repo_name=repo_name,
                    repo_url=repo_url
                )
                
                await ctx.info(
                    f"Successfully added repository '{result_repo_name}'",
                    extra={
                        'repo_name': result_repo_name,
                        'repo_url': repo_url
                    }
                )
                
                return {
                    'repository': result_repo_name,
                    'added': True,
                    'message': f"Repository '{result_repo_name}' added successfully"
                }
            
            except Exception as e:
                await ctx.error(
                    f"Failed to ensure repository: {str(e)}",
                    extra={
                        'repo_name': repo_name,
                        'repo_url': repo_url,
                        'error': str(e)
                    }
                )
                raise HelmOperationError(f'Failed to ensure repository: {str(e)}')
