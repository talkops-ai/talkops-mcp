"""Deployment overview resource."""

import json
from typing import Any, Dict
from tempo_mcp_server.resources.base import BaseResource


class DeploymentResources(BaseResource):
    """Deployment overview resource."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        config = self.config
        tempo_service = self.tempo_service

        @mcp_instance.resource(
            "tempo://deployment/overview",
            name="tempo_deployment_overview",
            description="Deployment topology: backends, modes, tenants, K8s",
            mime_type="application/json",
        )
        async def tempo_deployment_overview() -> str:
            overview: Dict[str, Any] = {
                "total_backends": len(config.backends),
                "backends": [],
                "kubernetes_enabled": config.kubernetes.enabled,
            }
            for backend in config.backends:
                overview["backends"].append({
                    "id": backend.id,
                    "type": backend.type,
                    "deployment_mode": backend.deployment_mode,
                    "multi_tenant": backend.multi_tenant,
                    "base_url": backend.base_url,
                })
            return json.dumps(overview, indent=2)
