"""Kargo project resources."""

import json
import yaml
from kargo_mcp_server.exceptions import KargoResourceError
from kargo_mcp_server.resources.base import BaseResource


class ProjectResources(BaseResource):
    """Project-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://projects",
            name="kargo_projects",
            description="List all Kargo projects in the cluster",
            mime_type="application/json",
        )
        async def list_projects_resource() -> str:
            """List all Kargo projects."""
            try:
                projects = await self.kargo_service.list_projects()
                if not projects:
                    return json.dumps({"message": "No projects found. Next step: Please verify your cluster configuration, or create a new Kargo project."})
                return json.dumps([p.model_dump() for p in projects], default=str, indent=2)
            except Exception as e:
                raise KargoResourceError(f"Failed to list projects: {e}")

        @mcp_instance.resource(
            "kargo://projects/{project_name}",
            name="kargo_project_detail",
            description="Get detailed project information including status and full YAML manifest",
            mime_type="text/markdown",
        )
        async def get_project_resource(project_name: str) -> str:
            """Get detailed project information."""
            try:
                project = await self.kargo_service.get_project(project_name)
                
                # Build summary details
                details = {
                    "name": project.get("metadata", {}).get("name", project_name),
                    "namespace": project.get("metadata", {}).get("namespace", ""),
                    "creationTimestamp": project.get("metadata", {}).get("creationTimestamp", ""),
                    "status": project.get("status", {}),
                }

                yaml_manifest = yaml.dump(
                    project,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

                output_parts = [
                    f"## Project Details: {project_name}",
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
                raise KargoResourceError(f"Failed to get project: {e}")
