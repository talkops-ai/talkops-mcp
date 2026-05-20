"""Prometheus TSDB cardinality resources."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource


class TsdbResources(BaseResource):
    """TSDB cardinality MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://tsdb/cardinality",
            name="prom_tsdb_cardinality",
            description="TSDB cardinality overview and top-N high-cardinality metrics for FinOps",
            mime_type="application/json",
        )
        async def tsdb_cardinality_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                summaries = {}
                for b in backends:
                    try:
                        summary = await self.prometheus_service.get_cardinality_summary(b.id)
                        summaries[b.id] = summary.model_dump()
                    except Exception:
                        summaries[b.id] = {"error": "Failed to fetch TSDB status"}
                return json.dumps(summaries, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get cardinality: {e}")
