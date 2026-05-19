"""Kargo freight resources."""

import json
import yaml
from kargo_mcp_server.exceptions import KargoResourceError
from kargo_mcp_server.resources.base import BaseResource


class FreightResources(BaseResource):
    """Freight-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://projects/{project}/freight",
            name="kargo_project_freight",
            description="List all freight in a Kargo project with artifact versions and stage states",
            mime_type="application/json",
        )
        async def list_freight_resource(project: str) -> str:
            """List all freight in a project."""
            try:
                freight = await self.kargo_service.list_freight(project)
                if not freight:
                    return json.dumps({"message": f"No freight found in project '{project}'. Next step: Use 'kargo_warehouse_mgmt' with action 'refresh' to trigger discovery, or verify the project name."})
                return json.dumps([f.model_dump() for f in freight], default=str, indent=2)
            except Exception as e:
                raise KargoResourceError(f"Failed to list freight: {e}")

        @mcp_instance.resource(
            "kargo://projects/{project}/freight/{freight_id}",
            name="kargo_freight_detail",
            description="Get detailed freight information including artifact references and full YAML manifest",
            mime_type="text/markdown",
        )
        async def get_freight_resource(project: str, freight_id: str) -> str:
            """Get detailed freight information."""
            try:
                freight = await self.kargo_service.get_freight(project, freight_id)
                
                details = {
                    "id": freight_id,
                    "project": project,
                    "status": freight.get("status", {}),
                }

                yaml_manifest = yaml.dump(
                    freight,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

                output_parts = [
                    f"## Freight Details: {freight_id}",
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
                raise KargoResourceError(f"Failed to get freight: {e}")
