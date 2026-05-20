"""Prometheus exporter catalog resource.

Exposes the built-in exporter registry as a browsable
MCP resource for host/user context injection.
"""

import json
from prometheus_mcp_server.config import SUPPORTED_EXPORTERS
from prometheus_mcp_server.resources.base import BaseResource


class ExporterResources(BaseResource):
    """Exporter catalog MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://exporters/catalog",
            name="prom_exporter_catalog",
            description="Built-in catalog of supported Prometheus exporters with types, ports, images, and environments",
            mime_type="application/json",
        )
        async def exporter_catalog_resource() -> str:
            catalog = [
                {
                    "name": info.type,
                    "description": info.description,
                    "default_ports": info.default_ports,
                    "supported_environments": info.supported_environments,
                    "image": info.image,
                    "default_scope": info.default_scope,
                }
                for info in SUPPORTED_EXPORTERS.values()
            ]
            return json.dumps(
                {"exporters": catalog, "total_count": len(catalog)},
                default=str, indent=2,
            )
