"""Kargo promotion task resources."""

import json
import yaml
from kargo_mcp_server.exceptions import KargoResourceError
from kargo_mcp_server.resources.base import BaseResource


class PromotionTaskResources(BaseResource):
    """PromotionTask-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "kargo://projects/{project}/promotiontasks",
            name="kargo_project_promotion_tasks",
            description="List all promotion tasks in a Kargo project. PromotionTasks define reusable promotion step sequences.",
            mime_type="application/json",
        )
        async def list_promotion_tasks_resource(project: str) -> str:
            """List all promotion tasks in a project."""
            try:
                tasks = await self.kargo_service.list_promotion_tasks(project)
                if not tasks:
                    return json.dumps({
                        "message": (
                            f"No promotion tasks found in project '{project}'. "
                            "Next step: Use 'kargo_promotion_task_mgmt' with action "
                            "'upsert' and a preset to create one."
                        )
                    })
                return json.dumps(tasks, default=str, indent=2)
            except Exception as e:
                raise KargoResourceError(f"Failed to list promotion tasks: {e}")

        @mcp_instance.resource(
            "kargo://projects/{project}/promotiontasks/{task_name}",
            name="kargo_promotion_task_detail",
            description="Get detailed promotion task information including steps, variables, and full YAML manifest",
            mime_type="text/markdown",
        )
        async def get_promotion_task_resource(project: str, task_name: str) -> str:
            """Get detailed promotion task information."""
            try:
                task = await self.kargo_service.get_promotion_task(project, task_name)

                # Extract key fields for the summary
                spec = task.get("spec", {})
                steps = spec.get("steps", [])
                task_vars = spec.get("vars", [])

                details = {
                    "name": task_name,
                    "project": project,
                    "step_count": len(steps),
                    "steps": [
                        s.get("uses", s.get("as", "unknown")) for s in steps
                    ],
                    "variables": [
                        {"name": v.get("name", ""), "value": v.get("value", "")}
                        for v in task_vars
                    ] if task_vars else [],
                }

                yaml_manifest = yaml.dump(
                    task,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

                output_parts = [
                    f"## PromotionTask Details: {task_name}",
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
                raise KargoResourceError(f"Failed to get promotion task: {e}")
