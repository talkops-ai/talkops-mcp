"""Kargo stage resources."""

import json
import yaml
from kargo_mcp_server.exceptions import KargoResourceError
from kargo_mcp_server.resources.base import BaseResource


class StageResources(BaseResource):
    """Stage-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://projects/{project}/stages",
            name="kargo_project_stages",
            description="List all stages in a Kargo project with DAG topology info",
            mime_type="application/json",
        )
        async def list_stages_resource(project: str) -> str:
            """List all stages in a project with DAG topology."""
            try:
                stages = await self.kargo_service.list_stages(project)
                if not stages:
                    return json.dumps({"message": f"No stages found in project '{project}'. Next step: Use 'kargo_stage_mgmt' with action 'upsert' to create a stage, or verify the project name."})
                return json.dumps([s.model_dump() for s in stages], default=str, indent=2)
            except Exception as e:
                raise KargoResourceError(f"Failed to list stages: {e}")

        @mcp_instance.resource(
            "kargo://projects/{project}/stages/{stage_name}",
            name="kargo_stage_detail",
            description="Get detailed stage information including health, current freight, and full YAML manifest",
            mime_type="text/markdown",
        )
        async def get_stage_resource(project: str, stage_name: str) -> str:
            """Get detailed stage information."""
            try:
                stage = await self.kargo_service.get_stage(project, stage_name)
                
                status_info = stage.get("status", {})
                
                details = {
                    "name": stage_name,
                    "project": project,
                    "current_freight": status_info.get("currentFreight", {}).get("name"),
                    "health": status_info.get("health", {}),
                    "phase": status_info.get("phase", "Unknown"),
                }

                yaml_manifest = yaml.dump(
                    stage,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

                output_parts = [
                    f"## Stage Details: {stage_name}",
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
                raise KargoResourceError(f"Failed to get stage: {e}")
