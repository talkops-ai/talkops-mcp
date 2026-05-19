"""Prometheus backend resources."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource


class BackendResources(BaseResource):
    """Backend-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://system/backends",
            name="prom_backends",
            description="List all known Prometheus-compatible backends and their health status",
            mime_type="application/json",
        )
        async def list_backends_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                result = []
                for b in backends:
                    health = await self.prometheus_service.check_health(b.id)
                    b.health = health  # type: ignore[assignment]
                    result.append(b.model_dump())
                return json.dumps({"backends": result}, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to list backends: {e}")

        @mcp_instance.resource(
            "prom://system/backends/{backend_id}",
            name="prom_backend_detail",
            description="Get detailed backend capabilities, runtime info, and health",
            mime_type="application/json",
        )
        async def get_backend_resource(backend_id: str) -> str:
            try:
                caps = await self.prometheus_service.get_backend_capabilities(backend_id)
                return json.dumps(caps.model_dump(), default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get backend: {e}")
