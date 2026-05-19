"""Kargo warehouse resources."""

import json
import yaml
from kargo_mcp_server.exceptions import KargoResourceError
from kargo_mcp_server.resources.base import BaseResource


class WarehouseResources(BaseResource):
    """Warehouse-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://projects/{project}/warehouses",
            name="kargo_project_warehouses",
            description="List all warehouses in a Kargo project with their artifact source types",
            mime_type="application/json",
        )
        async def list_warehouses_resource(project: str) -> str:
            """List all warehouses in a project."""
            try:
                warehouses = await self.kargo_service.list_warehouses(project)
                if not warehouses:
                    return json.dumps({"message": f"No warehouses found in project '{project}'. Next step: Use 'kargo_warehouse_mgmt' with action 'upsert' to create a warehouse with artifact subscriptions, or verify the project name."})
                return json.dumps([w.model_dump() for w in warehouses], default=str, indent=2)
            except Exception as e:
                raise KargoResourceError(f"Failed to list warehouses: {e}")

        @mcp_instance.resource(
            "kargo://projects/{project}/warehouses/{warehouse_name}",
            name="kargo_warehouse_detail",
            description="Get detailed warehouse information including subscriptions and full YAML manifest",
            mime_type="text/markdown",
        )
        async def get_warehouse_resource(project: str, warehouse_name: str) -> str:
            """Get detailed warehouse information."""
            try:
                warehouse = await self.kargo_service.get_warehouse(project, warehouse_name)
                
                details = {
                    "name": warehouse_name,
                    "project": project,
                    "status": warehouse.get("status", {}),
                }

                yaml_manifest = yaml.dump(
                    warehouse,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

                output_parts = [
                    f"## Warehouse Details: {warehouse_name}",
                    "",
                    "```json",
                    json.dumps(details, indent=2, default=str),
                    "```",
                    "",
                    "## Full YAML Manifest",
                    "",
                    "```yaml",
                    yaml_manifest.rstrip(),
                    "```",
                ]
                return "\n".join(output_parts)
            except Exception as e:
                raise KargoResourceError(f"Failed to get warehouse: {e}")
