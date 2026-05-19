"""Kargo diagnostics and observability tools."""

from typing import Dict, Any
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError
from kargo_mcp_server.tools.base import BaseTool


class DiagnosticsTools(BaseTool):
    """Tools for Kargo pipeline diagnostics and observability."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_describe_topology(
            project: str = Field(..., min_length=1, description="Kargo project name"),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Visualize the Kargo pipeline Directed Acyclic Graph (DAG) for a project.

            Use this tool to understand the architectural flow of a Kargo project before making mutations.
            It summarizes all stages, their upstream dependencies, downstream targets, root stages (entry points from warehouses), and leaf stages.
            Always run this when first onboarding to a new project to map out the promotion path.

            Args:
                project: Name of the Kargo project

            Returns:
                Topology summary dict with stage_count, roots, leaves, edges,
                and per-stage upstream/downstream lists
            """
            await ctx.info(f"Describing topology for project '{project}'")
            try:
                topology = await self.kargo_service.describe_topology(project)
                await ctx.info(
                    f"Topology: {topology.get('stage_count', 0)} stages",
                    extra={'project': project}
                )
                return topology
            except Exception as e:
                friendly_msg = (
                    f"Failed to describe topology: {str(e)}. "
                    "Use 'kargo_project_mgmt' to verify the project exists. "
                    "If the project is new, add stages using 'kargo_stage_mgmt'."
                )
                await ctx.error(friendly_msg)
                raise KargoOperationError(friendly_msg)
