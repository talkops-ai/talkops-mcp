"""Kargo warehouse tools.

Provides intelligent warehouse creation and management without requiring
users to know the underlying Kargo spec structure. Users describe their
artifact subscriptions using simple, flat parameters and the tool
automatically constructs the correct Kargo WarehouseSpec.
"""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import Field
from fastmcp import Context
from kargo_mcp_server.exceptions import KargoOperationError, KargoValidationError
from kargo_mcp_server.tools.base import BaseTool
from kargo_mcp_server.utils.warehouse_spec_builder import (
    build_warehouse_spec,
    SUBSCRIPTION_TYPES,
    FREIGHT_CREATION_POLICIES,
)


class WarehouseTools(BaseTool):
    """Tools for managing Kargo warehouses."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def kargo_warehouse_mgmt(
            action: Literal["list", "get", "refresh", "upsert"],
            project: str = Field(..., min_length=1, description="Kargo project name"),
            warehouse_name: Optional[str] = Field(
                None,
                description="Warehouse name (required for get, refresh, upsert)",
            ),
            subscriptions: Optional[List[Dict[str, Any]]] = Field(
                None,
                description=(
                    "List of artifact subscriptions (required for upsert). "
                    "Each dict must include 'type' (image, git, or chart) and "
                    "'repo_url'. Type-specific optional fields: "
                    "image: semver_constraint, image_selection_strategy, platform; "
                    "git: branch, semver_constraint, include_paths, exclude_paths; "
                    "chart: chart_name, semver_constraint."
                ),
            ),
            freight_creation_policy: Optional[str] = Field(
                None,
                description=(
                    "How Freight is created: 'Automatic' (default) creates Freight "
                    "on every new artifact discovery; 'Manual' requires explicit creation."
                ),
            ),
            interval: Optional[str] = Field(
                None,
                description=(
                    "Polling interval for artifact discovery, e.g. '5m0s' (default). "
                    "Uses Go duration format: '30s', '2m', '1h'."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Union[List[Dict[str, Any]], Dict[str, Any], str]:
            """Manage Kargo warehouses and trigger artifact discovery.

            Use this tool to list, retrieve, upsert, or refresh Kargo warehouses.
            A Warehouse subscribes to artifact sources (container images, Git repositories, Helm charts) and discovers new versions to produce Freight.

            Actions:
            - list: Discover all warehouses in a project.
            - get: Retrieve configuration and subscription details for a specific warehouse.
            - refresh: Force Kargo to immediately poll the warehouse's upstream artifact sources (Git/Docker) for new versions (requires allow_write=true).
            - upsert: Create or update a warehouse. Instead of providing a raw spec, describe your subscriptions using simple parameters and the tool builds the spec automatically (requires allow_write=true).

            Upsert example — create a warehouse watching a container image and a Git repo:
                action: "upsert"
                project: "my-project"
                warehouse_name: "my-warehouse"
                subscriptions: [
                    {"type": "image", "repo_url": "ghcr.io/org/app", "semver_constraint": "^1.0.0"},
                    {"type": "git", "repo_url": "https://github.com/org/repo.git", "branch": "main"}
                ]
            """
            if action in ["refresh", "upsert"] and not self.config.allow_write:
                raise KargoOperationError(
                    "Write operations are disabled. Set MCP_ALLOW_WRITE=true to enable."
                )

            if action in ["get", "refresh", "upsert"] and not warehouse_name:
                raise KargoValidationError(f"'warehouse_name' is required for action '{action}'")

            if action == "list":
                await ctx.info(
                    f"Listing warehouses for project '{project}'",
                    extra={'project': project}
                )
                try:
                    warehouses = await self.kargo_service.list_warehouses(project)
                    await ctx.info(
                        f"Found {len(warehouses)} warehouses",
                        extra={'project': project, 'count': len(warehouses)}
                    )
                    if not warehouses:
                        return [{
                            "message": (
                                f"No warehouses found in project '{project}'. "
                                "Use 'kargo_warehouse_mgmt' with action 'upsert' "
                                "to create a warehouse with artifact subscriptions."
                            )
                        }]
                    return [w.model_dump() for w in warehouses]
                except Exception as e:
                    friendly_msg = (
                        f"Failed to list warehouses: {str(e)}. "
                        "Use 'kargo_project_mgmt' to verify the project exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "get":
                if not isinstance(warehouse_name, str):
                    raise KargoValidationError("warehouse_name must be a string")
                await ctx.info(
                    f"Fetching warehouse '{warehouse_name}' in project '{project}'",
                    extra={'project': project, 'warehouse_name': warehouse_name}
                )
                try:
                    warehouse = await self.kargo_service.get_warehouse(project, warehouse_name)
                    await ctx.info(f"Successfully retrieved warehouse '{warehouse_name}'")
                    return warehouse
                except Exception as e:
                    friendly_msg = (
                        f"Failed to get warehouse '{warehouse_name}': {str(e)}. "
                        "Use 'kargo_warehouse_mgmt' with action 'list' to verify the warehouse exists."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "refresh":
                if not isinstance(warehouse_name, str):
                    raise KargoValidationError("warehouse_name must be a string")
                await ctx.info(
                    f"Refreshing warehouse '{warehouse_name}' in project '{project}'",
                    extra={'project': project, 'warehouse_name': warehouse_name}
                )
                try:
                    await self.kargo_service.refresh_warehouse(project, warehouse_name)
                    msg = f"Warehouse '{warehouse_name}' in project '{project}' scheduled for refresh."
                    await ctx.info(msg)
                    return msg
                except Exception as e:
                    friendly_msg = (
                        f"Failed to refresh warehouse '{warehouse_name}': {str(e)}. "
                        "Ensure the warehouse exists using 'kargo_warehouse_mgmt' with action 'get'."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            elif action == "upsert":
                if not isinstance(warehouse_name, str):
                    raise KargoValidationError("warehouse_name must be a string")

                # Normalize pydantic FieldInfo defaults to proper types.
                _subscriptions = subscriptions if isinstance(subscriptions, list) else None
                _policy = freight_creation_policy if isinstance(freight_creation_policy, str) else None
                _interval = interval if isinstance(interval, str) else None

                if not _subscriptions:
                    raise KargoValidationError(
                        "'subscriptions' is required for action 'upsert'. "
                        "Provide a list of subscription dicts, each with 'type' "
                        f"({', '.join(sorted(SUBSCRIPTION_TYPES))}) and 'repo_url'."
                    )

                await ctx.info(
                    f"Building warehouse spec for '{warehouse_name}' "
                    f"with {len(_subscriptions)} subscription(s)",
                    extra={
                        'project': project,
                        'warehouse_name': warehouse_name,
                        'subscription_count': len(_subscriptions),
                    }
                )

                # Build the spec from user-friendly parameters
                spec = build_warehouse_spec(
                    subscriptions=_subscriptions,
                    freight_creation_policy=_policy,
                    interval=_interval,
                )

                await ctx.info(
                    f"Upserting warehouse '{warehouse_name}' in project '{project}'",
                    extra={'project': project, 'warehouse_name': warehouse_name}
                )
                try:
                    warehouse = await self.kargo_service.upsert_warehouse(
                        project, warehouse_name, spec
                    )
                    msg = f"Successfully upserted warehouse '{warehouse_name}'"
                    await ctx.info(msg)
                    return {
                        "name": warehouse.metadata.name,
                        "namespace": warehouse.metadata.namespace,
                    }
                except KargoValidationError:
                    raise
                except Exception as e:
                    friendly_msg = (
                        f"Failed to upsert warehouse '{warehouse_name}': {str(e)}. "
                        "Verify that all subscription repo_urls are accessible "
                        "and credentials are configured if needed."
                    )
                    await ctx.error(friendly_msg)
                    raise KargoOperationError(friendly_msg)

            return {}
