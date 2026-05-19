"""Kargo promotion resources."""

import json
import yaml
from kargo_mcp_server.exceptions import KargoResourceError
from kargo_mcp_server.resources.base import BaseResource


class PromotionResources(BaseResource):
    """Promotion-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://projects/{project}/promotions",
            name="kargo_project_promotions",
            description="List all promotions in a Kargo project with their status",
            mime_type="application/json",
        )
        async def list_promotions_resource(project: str) -> str:
            """List all promotions in a project."""
            try:
                promotions = await self.kargo_service.list_promotions(project)
                if not promotions:
                    return json.dumps({"message": f"No promotions found in project '{project}'. Next step: Use 'kargo_promotion_mgmt' with action 'create' to promote freight, or verify the project name."})
                return json.dumps([p.model_dump() for p in promotions], default=str, indent=2)
            except Exception as e:
                raise KargoResourceError(f"Failed to list promotions: {e}")

        @mcp_instance.resource(
            "kargo://projects/{project}/promotions/{promotion_name}",
            name="kargo_promotion_detail",
            description="Get detailed promotion information including step-by-step status and full YAML manifest",
            mime_type="text/markdown",
        )
        async def get_promotion_resource(project: str, promotion_name: str) -> str:
            """Get detailed promotion information."""
            try:
                promotion = await self.kargo_service.get_promotion(project, promotion_name)
                
                details = {
                    "name": promotion_name,
                    "project": project,
                    "stage": promotion.get("spec", {}).get("stage"),
                    "freight": promotion.get("spec", {}).get("freight"),
                    "status": promotion.get("status", {}),
                }

                yaml_manifest = yaml.dump(
                    promotion,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

                output_parts = [
                    f"## Promotion Details: {promotion_name}",
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
                raise KargoResourceError(f"Failed to get promotion: {e}")
