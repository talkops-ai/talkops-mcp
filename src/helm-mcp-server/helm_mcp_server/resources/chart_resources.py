"""Helm repository and chart metadata resources."""

from __future__ import annotations

from typing import Any, Dict

from helm_mcp_server.exceptions import HelmResourceError, HelmResourceNotFoundError
from helm_mcp_server.resources.base import BaseResource


class ChartResources(BaseResource):
    """URI-addressed resources for configured Helm repositories and chart metadata/values/README."""

    def register(self, mcp_instance: Any) -> None:
        """Register chart and repository resources with FastMCP."""

        @mcp_instance.resource(
            "helm://repositories",
            mime_type="application/json",
        )
        async def list_repositories() -> Dict[str, Any]:
            """List all configured Helm chart repositories."""
            try:
                repos = await self.helm_service.list_repositories()
                return {
                    "repositories": repos,
                    "count": len(repos),
                }
            except Exception as exc:
                raise HelmResourceError(
                    f"Failed to list Helm repositories: {exc}. "
                    "Call helm_ensure_repository to add a repository."
                )

        @mcp_instance.resource(
            "helm://charts/{repository}/{chart_name}",
            mime_type="application/json",
        )
        async def get_chart_metadata(repository: str, chart_name: str) -> Dict[str, Any]:
            """Get Chart.yaml metadata and sub-chart dependencies for a specific chart."""
            try:
                return await self.helm_service.get_chart_info(
                    chart_name=chart_name,
                    repository=repository,
                )
            except Exception as exc:
                raise HelmResourceNotFoundError(
                    f"Chart '{repository}/{chart_name}' not found: {exc}. "
                    f"Call helm_search_charts(query='{chart_name}') or read 'helm://repositories'."
                )

        @mcp_instance.resource(
            "helm://charts/{repository}/{chart_name}/values",
            mime_type="application/json",
        )
        async def get_chart_default_values(repository: str, chart_name: str) -> Dict[str, Any]:
            """Get default values.yaml structure for a specific Helm chart."""
            try:
                return await self.helm_service.get_chart_values(
                    chart_name=chart_name,
                    repository=repository,
                )
            except Exception as exc:
                raise HelmResourceNotFoundError(
                    f"Default values for chart '{repository}/{chart_name}' not found: {exc}. "
                    f"Call helm_search_charts(query='{chart_name}') to verify chart availability."
                )

        @mcp_instance.resource(
            "helm://charts/{repository}/{chart_name}/readme",
            mime_type="text/markdown",
        )
        async def get_chart_readme(repository: str, chart_name: str) -> str:
            """Get the README documentation for a specific Helm chart."""
            try:
                readme_text = await self.helm_service.get_chart_readme(
                    chart_name=chart_name,
                    repository=repository,
                )
                if not readme_text or not readme_text.strip():
                    raise HelmResourceNotFoundError(
                        f"Chart README is empty for '{repository}/{chart_name}'. "
                        f"Read 'helm://charts/{repository}/{chart_name}/values' for configuration keys."
                    )
                return readme_text
            except HelmResourceNotFoundError:
                raise
            except Exception as exc:
                raise HelmResourceNotFoundError(
                    f"Chart README not found for '{repository}/{chart_name}': {exc}. "
                    f"Read 'helm://charts/{repository}/{chart_name}' for metadata instead."
                )
