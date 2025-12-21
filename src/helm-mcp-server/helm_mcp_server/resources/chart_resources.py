"""Helm chart-related resources."""

import json
import asyncio
from typing import List, Optional
from mcp.types import Resource, TextContent
from helm_mcp_server.exceptions import HelmResourceError, HelmResourceNotFoundError, HelmOperationError
from helm_mcp_server.resources.base import BaseResource


class ChartResources(BaseResource):
    """Helm chart resources."""
    
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP."""
        
        @mcp_instance.resource("helm://charts")
        async def list_available_charts() -> List[Resource]:
            """List all available charts in configured repositories.
            
            Returns dynamic resources for each chart.
            """
            try:
                # Search for all charts (empty query returns all)
                charts = await self.helm_service.search_charts(
                    query='',
                    repository='bitnami',
                    limit=100  # Get more charts for listing
                )
                
                return [
                    Resource(
                        uri=f"helm://charts/{chart.get('repository', 'bitnami')}/{chart.get('name', 'unknown')}",
                        name=f"Chart: {chart.get('name', 'unknown')}",
                        description=f"Helm chart {chart.get('name', 'unknown')} from {chart.get('repository', 'bitnami')} repository",
                        mimeType="application/json",
                        contents=[
                            TextContent(
                                text=json.dumps(chart, indent=2),
                                mimeType="application/json"
                            )
                        ]
                    )
                    for chart in charts
                ]
            except Exception as e:
                # Return empty list on error
                return []
        
        @mcp_instance.resource(
            "helm://charts/{repository}/{chart_name}",
            mime_type="application/json"
        )
        async def get_chart_metadata(repository: str, chart_name: str) -> dict:
            """Get metadata for a specific chart.
            
            Args:
                repository: Helm repository name
                chart_name: Chart name
            
            Returns:
                Dictionary with chart metadata
            
            Raises:
                HelmResourceNotFoundError: If chart not found
            """
            try:
                # Get chart info from Helm service
                chart_info = await self.helm_service.get_chart_info(
                    chart_name=chart_name,
                    repository=repository
                )
                
                # Return dict directly - FastMCP will convert to JSON automatically
                return chart_info
            except Exception as e:
                raise HelmResourceNotFoundError(f"Chart not found: {repository}/{chart_name}")
        
        @mcp_instance.resource(
            "helm://charts/{repository}/{chart_name}/readme",
            mime_type="text/markdown"
        )
        async def get_chart_readme(repository: str, chart_name: str) -> str:
            """Get the README for a Helm chart.
            
            Args:
                repository: Helm repository name
                chart_name: Chart name
            
            Returns:
                Chart README as markdown string
            
            Raises:
                HelmResourceNotFoundError: If chart not found
            """
            try:
                # Use HelmService method which handles repository checking and error handling
                readme_text = await self.helm_service.get_chart_readme(
                    chart_name=chart_name,
                    repository=repository
                )
                
                if not readme_text or not readme_text.strip():
                    raise HelmResourceNotFoundError(
                        f"Chart README is empty for {repository}/{chart_name}. "
                        f"The chart may not have a README file."
                    )
                
                # Return string directly - FastMCP will convert to TextContent automatically
                return readme_text
            except HelmOperationError as e:
                # Convert HelmOperationError to HelmResourceNotFoundError for consistency
                error_str = str(e)
                if 'not found' in error_str.lower():
                    raise HelmResourceNotFoundError(
                        f"Chart not found: {repository}/{chart_name}. {error_str}"
                    )
                raise HelmResourceError(f"Failed to get chart README: {error_str}")
            except HelmResourceNotFoundError:
                raise
            except Exception as e:
                raise HelmResourceError(f"Failed to get chart README: {str(e)}")

