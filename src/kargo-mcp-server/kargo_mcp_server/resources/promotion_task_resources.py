"""Kargo PromotionTask and ClusterPromotionTask sanitized YAML resources."""

import json
import yaml
from typing import Any

from kargo_mcp_server.resources.base import BaseResource
from kargo_mcp_server.utils.redaction import sanitize_manifest


class PromotionTaskResources(BaseResource):
    """PromotionTask and ClusterPromotionTask MCP resources."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://projects/{project}/promotion-tasks/{task}",
            name="kargo_promotion_task_detail",
            description="Sanitized YAML manifest for a project PromotionTask",
            mime_type="application/x-yaml",
        )
        async def get_promotion_task_resource(project: str, task: str) -> str:
            """Return sanitized YAML manifest for a PromotionTask."""
            try:
                raw = await self.kargo_service.get_promotion_task(project, task)
                sanitized = sanitize_manifest(raw)
                return yaml.dump(sanitized, default_flow_style=False)
            except Exception as exc:
                return json.dumps(
                    {"project": project, "task": task, "error": str(exc)},
                    indent=2,
                )

        @mcp_instance.resource(
            "kargo://cluster-promotion-tasks/{task}",
            name="kargo_cluster_promotion_task_detail",
            description="Sanitized YAML manifest for a cluster-scoped ClusterPromotionTask",
            mime_type="application/x-yaml",
        )
        async def get_cluster_promotion_task_resource(task: str) -> str:
            """Return sanitized YAML manifest for a ClusterPromotionTask."""
            try:
                raw = await self.kargo_service.get_cluster_promotion_task(task)
                sanitized = sanitize_manifest(raw)
                return yaml.dump(sanitized, default_flow_style=False)
            except Exception as exc:
                return json.dumps({"task": task, "error": str(exc)}, indent=2)
