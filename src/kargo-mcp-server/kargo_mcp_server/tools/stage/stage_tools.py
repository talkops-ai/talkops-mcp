"""Kargo stage tools."""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError, KargoValidationError
from kargo_mcp_server.models.stage import (
    StageSpec,
    RequestedFreight,
    RequestedFreightOrigin,
    FreightSources,
)
from kargo_mcp_server.tools.base import BaseTool


class StageTools(BaseTool):
    """Tools for managing Kargo stages."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_stage_mgmt(
            action: Literal["list", "get", "upsert", "reverify"],
            project: str = Field(..., min_length=1, description="Kargo project name"),
            stage_name: Optional[str] = Field(None, description="Stage name (required for get, upsert, reverify)"),
            requested_freight_origins: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "List of freight origins for upsert. Each entry must have 'kind' (always 'Warehouse') "
                    "and 'name' (warehouse name). Optionally include 'stages' (list of upstream stage names) "
                    "to define the promotion DAG. Example root stage: [{\"kind\": \"Warehouse\", \"name\": \"wh\"}]. "
                    "Example downstream stage: [{\"kind\": \"Warehouse\", \"name\": \"wh\", \"stages\": [\"dev\"]}]."
                )
            ),
            promotion_template_ref: Optional[str] = Field(
                default=None,
                description="Name of the PromotionTask to reference (used in upsert)"
            ),
            variables: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Stage variables for promotion templates (used in upsert)"
            ),
            ctx: Context = None  # type: ignore[assignment]
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Manage Kargo stages and trigger stage-specific verifications.

            Use this tool to list, retrieve, create/update (upsert), or reverify Kargo stages.
            A Stage represents a promotion target in the pipeline DAG (e.g., dev, staging, production).

            Actions:
            - list: Discover all stages within a project to understand the topology.
            - get: Check the health, current freight, and status of a specific stage.
            - upsert: Create a new stage or update an existing one (requires allow_write=true).
            - reverify: Re-run verification tests for the freight currently deployed in a stage. Useful if tests were flaky (requires allow_write=true).

            Args:
                action: Operation to perform (list, get, upsert, reverify)
                project: Name of the Kargo project
                stage_name: Name of the stage (required for get, upsert, reverify)
                requested_freight_origins: Freight origin specifications for upsert.
                    Each entry specifies a Warehouse origin and optional upstream stages.
                    Format: [{"kind": "Warehouse", "name": "<warehouse>"}] for root stages,
                    or [{"kind": "Warehouse", "name": "<warehouse>", "stages": ["<upstream-stage>"]}]
                    for stages that receive freight from upstream stages.
                promotion_template_ref: PromotionTask reference name for upsert
                variables: Stage template variables for upsert

            Returns:
                Depends on the action requested.
            """
            if action in ["upsert", "reverify"] and not self.config.allow_write:
                raise KargoOperationError(
                    "Write operations are disabled. Set MCP_ALLOW_WRITE=true to enable."
                )

            if action in ["get", "upsert", "reverify"] and not stage_name:
                raise KargoValidationError(f"'stage_name' is required for action '{action}'")

            if action == "list":
                await ctx.info(
                    f"Listing stages for project '{project}'",
                    extra={'project': project}
                )
                try:
                    stages = await self.kargo_service.list_stages(project)
                    await ctx.info(
                        f"Found {len(stages)} stages in project '{project}'",
                        extra={'project': project, 'count': len(stages)}
                    )
                    if not stages:
                        return [{"message": f"No stages found in project '{project}'. Next step: Use 'kargo_stage_mgmt' with action 'upsert' to create a stage, or verify the project name."}]
                    return [s.model_dump() for s in stages]
                except Exception as e:
                    friendly_msg = (
                        f"Failed to list stages: {str(e)}. "
                        "Use 'kargo_project_mgmt' to verify the project exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "get":
                # Ensure stage_name is strings to satisfy pyright
                if not isinstance(stage_name, str):
                    raise KargoValidationError("stage_name must be a string")
                await ctx.info(
                    f"Fetching stage '{stage_name}' in project '{project}'",
                    extra={'project': project, 'stage_name': stage_name}
                )
                try:
                    stage = await self.kargo_service.get_stage(project, stage_name)
                    await ctx.info(f"Successfully retrieved stage '{stage_name}'")
                    return stage
                except Exception as e:
                    friendly_msg = (
                        f"Failed to get stage '{stage_name}': {str(e)}. "
                        "Use 'kargo_stage_mgmt' with action 'list' to verify the stage exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "upsert":
                if not isinstance(stage_name, str):
                    raise KargoValidationError("stage_name must be a string")

                # Normalize FieldInfo defaults
                _origins = requested_freight_origins if isinstance(requested_freight_origins, list) else None
                _promo_ref = promotion_template_ref if isinstance(promotion_template_ref, str) else None
                _variables = variables if isinstance(variables, dict) else None

                await ctx.info(
                    f"Upserting stage '{stage_name}' in project '{project}'",
                    extra={'project': project, 'stage_name': stage_name}
                )
                try:
                    freight_list = _build_requested_freight(_origins or [])

                    # Build the promotion template if a ref is provided
                    promo_template = None
                    if _promo_ref:
                        promo_template = {
                            "spec": {
                                "steps": [
                                    {
                                        "task": {
                                            "name": _promo_ref,
                                        }
                                    }
                                ]
                            }
                        }

                    spec = StageSpec(
                        variables=_variables or {},
                        requestedFreight=freight_list,
                        promotionTemplate=promo_template,
                    )
                    stage_res = await self.kargo_service.upsert_stage(
                        project, stage_name, spec.model_dump(by_alias=True, exclude_none=True)
                    )
                    await ctx.info(f"Successfully upserted stage '{stage_name}'")
                    return {
                        "name": stage_res.metadata.name,
                        "namespace": stage_res.metadata.namespace,
                        "current_freight_id": (
                            stage_res.status.current_freight_id if stage_res.status else None
                        ),
                    }
                except ValueError as e:
                    raise KargoValidationError(str(e))
                except Exception as e:
                    friendly_msg = (
                        f"Failed to upsert stage '{stage_name}': {str(e)}. "
                        "Check that the freight origins are valid."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "reverify":
                if not isinstance(stage_name, str):
                    raise KargoValidationError("stage_name must be a string")
                await ctx.info(f"Re-verifying stage '{stage_name}' in project '{project}'")
                try:
                    updated = await self.kargo_service.reverify_stage(project, stage_name)
                    await ctx.info(f"Verification triggered for stage '{stage_name}'")
                    return {
                        "name": updated.metadata.name,
                        "current_freight_id": (
                            updated.status.current_freight_id if updated.status else None
                        ),
                    }
                except Exception as e:
                    friendly_msg = (
                        f"Failed to reverify stage '{stage_name}': {str(e)}. "
                        "Ensure the stage has current freight."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)
            
            return {}


def _build_requested_freight(
    origins: List[Dict[str, Any]],
) -> List[RequestedFreight]:
    """Convert user-friendly origin dicts to proper Kargo RequestedFreight models.

    In Kargo's API, ``requestedFreight[].origin`` must always reference a
    **Warehouse**.  Stage-to-stage dependencies are expressed through
    ``requestedFreight[].sources.stages`` (a list of upstream Stage names).

    This function provides backward-compatible translation:

    1. ``{"kind": "Warehouse", "name": "wh"}`` → root stage, direct from warehouse.
    2. ``{"kind": "Warehouse", "name": "wh", "stages": ["dev"]}`` → receives
       freight from the "dev" stage (the correct Kargo structure).
    3. ``{"kind": "Stage", "name": "dev"}`` → **legacy shorthand** (deprecated).
       This is auto-corrected: since the user did not specify a warehouse,
       we cannot guess one, so we raise a validation error.

    Args:
        origins: List of dicts, each with 'kind', 'name', and optionally 'stages'.

    Returns:
        List of RequestedFreight models ready for the Kargo API.

    Raises:
        KargoValidationError: If the origin is invalid.
    """
    freight_list: List[RequestedFreight] = []

    for rf in origins:
        kind = rf.get("kind", "Warehouse")
        name = rf.get("name", "")
        upstream_stages: List[str] = rf.get("stages", [])

        if not name:
            raise KargoValidationError(
                "Each freight origin must have a 'name'. "
                "Example: {\"kind\": \"Warehouse\", \"name\": \"my-warehouse\"}"
            )

        if kind == "Stage":
            raise KargoValidationError(
                f"Cannot use kind='Stage' for origin '{name}'. "
                "In Kargo, origins must always be Warehouses. "
                "To specify upstream stages, use: "
                "{\"kind\": \"Warehouse\", \"name\": \"<warehouse>\", "
                "\"stages\": [\"<upstream-stage-name>\"]}"
            )

        if kind != "Warehouse":
            raise KargoValidationError(
                f"Invalid origin kind '{kind}'. "
                "Origin kind must be 'Warehouse'."
            )

        # Determine sources: if upstream stages are specified, freight
        # flows through those stages. Otherwise, it comes directly
        # from the warehouse.
        sources = FreightSources(
            direct=len(upstream_stages) == 0,
            stages=upstream_stages,
        )

        freight_list.append(
            RequestedFreight(
                origin=RequestedFreightOrigin(kind="Warehouse", name=name),
                sources=sources,
            )
        )

    return freight_list
