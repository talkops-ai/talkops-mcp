"""Kargo freight tools."""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError, KargoValidationError
from kargo_mcp_server.tools.base import BaseTool


class FreightTools(BaseTool):
    """Tools for managing Kargo freight."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_freight_mgmt(
            action: Literal["list", "get", "approve"],
            project: str = Field(..., min_length=1, description="Kargo project name"),
            freight_id: Optional[str] = Field(None, description="Freight ID (required for get, approve)"),
            stage: Optional[str] = Field(None, description="Target stage for approval (required for approve)"),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Manage Kargo freight and handle manual stage approvals.

            Use this tool to list, retrieve, or approve Kargo freight.
            Freight represents a specific set of versioned artifact references (Git commits, image digests, chart versions) discovered by a Warehouse.

            Actions:
            - list: Discover all available freight in a project and see which stages they have passed.
            - get: Inspect the exact Git SHAs, image digests, and chart versions inside a specific freight payload.
            - approve: Manually mark a piece of freight as approved for deployment to a specific target stage (requires allow_write=true).

            Args:
                action: Operation to perform (list, get, approve)
                project: Name of the Kargo project
                freight_id: ID of the freight (required for get, approve)
                stage: Target stage name (required for approve)

            Returns:
                Depends on the action requested.
            """
            if action == "approve" and not self.config.allow_write:
                raise KargoOperationError(
                    "Write operations are disabled. Set MCP_ALLOW_WRITE=true to enable."
                )

            if action in ["get", "approve"] and not freight_id:
                raise KargoValidationError(f"'freight_id' is required for action '{action}'")
            if action == "approve" and not stage:
                raise KargoValidationError(f"'stage' is required for action '{action}'")

            if action == "list":
                await ctx.info(f"Listing freight for project '{project}'", extra={'project': project})
                try:
                    freight = await self.kargo_service.list_freight(project)
                    await ctx.info(f"Found {len(freight)} freight items", extra={'count': len(freight)})
                    if not freight:
                        return [{"message": f"No freight found in project '{project}'. Next step: Use 'kargo_warehouse_mgmt' to trigger discovery."}]
                    return [f.model_dump() for f in freight]
                except Exception as e:
                    friendly_msg = (
                        f"Failed to list freight: {str(e)}. "
                        "Use 'kargo_project_mgmt' to verify the project exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "get":
                if not isinstance(freight_id, str):
                    raise KargoValidationError("freight_id must be a string")
                await ctx.info(f"Fetching freight '{freight_id}'", extra={'freight_id': freight_id})
                try:
                    freight_obj = await self.kargo_service.get_freight(project, freight_id)
                    await ctx.info(f"Successfully retrieved freight '{freight_id}'")
                    return freight_obj
                except Exception as e:
                    friendly_msg = (
                        f"Failed to get freight '{freight_id}': {str(e)}. "
                        "Use 'kargo_freight_mgmt' with action 'list' to verify the freight ID exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "approve":
                if not isinstance(freight_id, str) or not isinstance(stage, str):
                    raise KargoValidationError("freight_id and stage must be strings")
                await ctx.info(f"Approving freight '{freight_id}' for stage '{stage}'")
                try:
                    freight_res = await self.kargo_service.approve_freight(
                        project=project, freight_id=freight_id, stage=stage,
                    )
                    await ctx.info(f"Successfully approved freight '{freight_id}' for stage '{stage}'")
                    return {
                        "id": freight_res.metadata.name,
                        "artifacts": [a.model_dump() for a in freight_res.spec.artifacts],
                        "per_stage": (
                            [s.model_dump() for s in freight_res.status.stage_states]
                            if freight_res.status else []
                        ),
                    }
                except Exception as e:
                    friendly_msg = (
                        f"Failed to approve freight '{freight_id}': {str(e)}. "
                        "Verify freight ID and stage using 'kargo_freight_mgmt' and 'kargo_stage_mgmt'."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)
            
            return {}
