"""Prometheus metric metadata resources."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource


class MetadataResources(BaseResource):
    """Metric metadata MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://metadata/catalog",
            name="prom_metric_catalog",
            description="Catalog of metric names with type and HELP text, used to prevent metric name hallucination",
            mime_type="application/json",
        )
        async def metric_catalog_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                catalogs = {}
                for b in backends:
                    try:
                        catalog = await self.prometheus_service.get_metric_catalog(b.id)
                        catalogs[b.id] = catalog.model_dump()
                    except Exception:
                        catalogs[b.id] = {"error": "Failed to fetch metadata"}
                return json.dumps(catalogs, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get metric catalog: {e}")
