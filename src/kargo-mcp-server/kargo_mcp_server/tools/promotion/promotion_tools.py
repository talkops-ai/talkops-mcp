"""Kargo promotion tools."""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError, KargoValidationError
from kargo_mcp_server.tools.base import BaseTool


class PromotionTools(BaseTool):
    """Tools for managing Kargo promotions."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_promotion_mgmt(
            action: Literal["list", "get", "create", "abort"],
            project: str = Field(..., min_length=1, description="Kargo project name"),
            promotion_name: Optional[str] = Field(None, description="Promotion name (required for get, abort)"),
            stage: Optional[str] = Field(None, description="Target stage name (required for create)"),
            freight_id: Optional[Union[str, List[str]]] = Field(
                None,
                description=(
                    "Freight ID(s) to promote (required for create). "
                    "Pass a single freight name, or a list of freight names for "
                    "multi-origin stages. When multiple freight IDs are provided, "
                    "one Promotion is created per freight ID in sequence."
                ),
            ),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Manage Kargo promotions and orchestrate deployments.

            Use this tool to list, retrieve, create, or abort Kargo promotions.
            A Promotion is a request to transition Freight into a Stage, executing the necessary deployment steps (e.g., Kustomize builds, ArgoCD syncs).

            Actions:
            - list: Discover all past and active promotions in a project.
            - get: Monitor the detailed step-by-step progress, phase, and health of a specific promotion.
            - create: Trigger the deployment of a specific freight to a target stage (requires allow_write=true).
              For multi-origin stages that require multiple pieces of Freight,
              pass all required freight IDs as a list — one Promotion is created per ID.
            - abort: Stop a currently running or stuck promotion task (requires allow_write=true).

            Args:
                action: Operation to perform (list, get, create, abort)
                project: Name of the Kargo project
                promotion_name: Name of the promotion (required for get, abort)
                stage: Target stage name (required for create)
                freight_id: Freight name(s) to promote (required for create). A single
                    string or a list of strings for multi-origin stages.

            Returns:
                Depends on the action requested.
            """
            if action in ["create", "abort"] and not self.config.allow_write:
                raise KargoOperationError(
                    "Write operations are disabled. Set MCP_ALLOW_WRITE=true to enable."
                )

            if action in ["get", "abort"] and promotion_name is None:
                raise KargoValidationError(f"'promotion_name' is required for action '{action}'")
            if action == "create":
                if stage is None:
                    raise KargoValidationError("'stage' is required for action 'create'")
                if freight_id is None:
                    raise KargoValidationError("'freight_id' is required for action 'create'")

            if action == "list":
                await ctx.info(f"Listing promotions for project '{project}'")
                try:
                    promotions = await self.kargo_service.list_promotions(project)
                    await ctx.info(f"Found {len(promotions)} promotions")
                    if not promotions:
                        return [{"message": f"No promotions found in project '{project}'. Next step: Use 'kargo_promotion_mgmt' with action 'create' to promote freight."}]
                    return [p.model_dump() for p in promotions]
                except Exception as e:
                    friendly_msg = (
                        f"Failed to list promotions: {str(e)}. "
                        "Use 'kargo_project_mgmt' to verify the project exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "get":
                if not isinstance(promotion_name, str):
                    raise KargoValidationError("promotion_name must be a string")
                await ctx.info(f"Fetching promotion '{promotion_name}'")
                try:
                    promotion = await self.kargo_service.get_promotion(project, promotion_name)
                    await ctx.info(f"Successfully retrieved promotion '{promotion_name}'")
                    return promotion
                except Exception as e:
                    friendly_msg = (
                        f"Failed to get promotion '{promotion_name}': {str(e)}. "
                        "Use 'kargo_promotion_mgmt' with action 'list' to verify the promotion exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "create":
                # Normalise to a list so the loop works for both single and multi-freight
                freight_ids: List[str] = (
                    freight_id if isinstance(freight_id, list) else [freight_id]  # type: ignore[list-item]
                )
                # Validate all entries are non-empty strings
                for fid in freight_ids:
                    if not isinstance(fid, str) or not fid.strip():
                        raise KargoValidationError(
                            f"Every freight_id must be a non-empty string, got: {fid!r}"
                        )

                await ctx.info(
                    f"Creating {'1 promotion' if len(freight_ids) == 1 else f'{len(freight_ids)} sequential promotions'}: "
                    f"freight {freight_ids!r} -> stage '{stage}'"
                )

                results: List[Dict[str, Any]] = []
                try:
                    for fid in freight_ids:
                        await ctx.info(f"Promoting freight '{fid}' -> stage '{stage}'")
                        promotion_res = await self.kargo_service.create_promotion(
                            project=project, stage=stage, freight=fid  # type: ignore[arg-type]
                        )
                        result_entry = {
                            "name": promotion_res.metadata.name,
                            "stage": promotion_res.spec.stage,
                            "freight": promotion_res.spec.freight,
                            "state": promotion_res.status.state if promotion_res.status else "Unknown",
                        }
                        results.append(result_entry)
                        await ctx.info(f"Promotion created: {promotion_res.metadata.name}")
                except Exception as e:
                    # If it's an ApiError, the raw Kargo JSON response is in e.body
                    raw_body = getattr(e, "body", "")
                    friendly_msg = (
                        f"Failed to create promotion: {str(e)}. "
                        f"Raw API Response: {raw_body}\n"
                        "Ensure the freight is approved for the target stage using "
                        "'kargo_freight_mgmt'. Use 'kargo_freight_mgmt' and "
                        "'kargo_stage_mgmt' to verify the IDs."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

                # Return a single dict for single freight, a list for multi-freight
                if len(results) == 1:
                    return results[0]
                return results

            elif action == "abort":
                if not isinstance(promotion_name, str):
                    raise KargoValidationError("promotion_name must be a string")
                await ctx.info(f"Aborting promotion '{promotion_name}'")
                try:
                    promotion_res = await self.kargo_service.abort_promotion(project, promotion_name)
                    await ctx.info(f"Promotion '{promotion_name}' aborted")
                    return {
                        "name": promotion_res.metadata.name,
                        "stage": promotion_res.spec.stage,
                        "freight": promotion_res.spec.freight,
                        "state": promotion_res.status.state if promotion_res.status else "Unknown",
                    }
                except Exception as e:
                    friendly_msg = (
                        f"Failed to abort promotion '{promotion_name}': {str(e)}. "
                        "Ensure the promotion is in 'Pending' or 'Running' state. "
                        "Use 'kargo_promotion_mgmt' with action 'get' to check its current state."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)
            
            return {}
