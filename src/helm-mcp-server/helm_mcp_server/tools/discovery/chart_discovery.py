"""Helm chart discovery tools."""

from typing import Dict, Any, List, Optional, Union
from pydantic import Field
from fastmcp import Context
from helm_mcp_server.exceptions import HelmOperationError
from helm_mcp_server.tools.base import BaseTool


class ChartDiscoveryTools(BaseTool):
    """Tools for discovering Helm charts."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def helm_search_charts(
            query: str = Field(..., description='Chart name or keyword'),
            repository: str = Field(default='bitnami', description='Helm repository name'),
            limit: int = Field(default=10, ge=1, le=50, description='Maximum results'),
            ctx: Context = None
        ) -> Union[List[Dict], str]:
            """Search for Helm charts.
            
            Args:
                query: Chart name or keyword
                repository: Helm repository name
                limit: Maximum results
            
            Returns:
                List of chart metadata, or a message string if no charts found
            
            Raises:
                HelmOperationError: If search fails
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
        
        @mcp_instance.tool()
        async def helm_get_chart_info(
            chart_name: str = Field(..., description='Chart name'),
            repository: str = Field(default='bitnami'),
            ctx: Context = None
        ) -> Dict:
            """Get detailed chart information.
            
            Args:
                chart_name: Name of the chart
                repository: Helm repository name
            
            Returns:
                Detailed chart information
            
            Raises:
                HelmOperationError: If getting chart info fails
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

        @mcp_instance.tool()
        async def helm_get_chart_values_schema(
            chart_name: str = Field(..., description='Chart name'),
            repository: str = Field(default='bitnami', description='Helm repository name'),
            version: Optional[str] = Field(default=None, description='Specific chart version'),
            ctx: Context = None
        ) -> Dict:
            """Get the values schema (validation rules) for a Helm chart.
            
            Args:
                chart_name: Name of the chart
                repository: Helm repository name
                version: Specific chart version
            
            Returns:
                Dictionary containing the default values (acting as schema)
            
            Raises:
                HelmOperationError: If getting values fails
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
        
        @mcp_instance.tool()
        async def helm_ensure_repository(
            repo_name: str = Field(..., description='Repository name'),
            repo_url: Optional[str] = Field(default=None, description='Repository URL (if None, will try to get from known repos)'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Ensure a Helm repository exists, adding it if necessary.
            
            This tool checks if a Helm repository exists, and if not, adds it automatically.
            If no URL is provided, it will try to use a known repository URL for common repositories
            (bitnami, argo, prometheus-community, grafana, ingress-nginx, jetstack).
            
            Args:
                repo_name: Repository name
                repo_url: Repository URL (optional, will be auto-detected for known repos)
            
            Returns:
                Dictionary containing:
                - 'repository': Repository name that was used
                - 'added': Boolean indicating if repository was newly added
                - 'message': Status message
            
            Raises:
                HelmOperationError: If repository cannot be added
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

