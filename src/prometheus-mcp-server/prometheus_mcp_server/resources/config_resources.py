"""Prometheus runtime configuration resources."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource


class ConfigResources(BaseResource):
    """Runtime configuration MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://config/runtime",
            name="prom_runtime_config",
            description="Sanitized runtime configuration: global settings, remote-write targets, and TSDB stats",
            mime_type="application/json",
        )
        async def runtime_config_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                configs = {}
                for b in backends:
                    try:
                        config = await self.prometheus_service.get_config(b.id)
                        configs[b.id] = config.model_dump()
                    except Exception:
                        configs[b.id] = {"error": "Failed to fetch config"}
                return json.dumps(configs, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get runtime config: {e}")
