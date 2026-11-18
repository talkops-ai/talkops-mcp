"""Prometheus topology resources (scrape targets and service health)."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource


class TopologyResources(BaseResource):
    """Topology-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://topology/targets",
            name="prom_topology_targets",
            description="Scrape target health summary grouped by job/service plus failing target endpoints",
            mime_type="application/json",
        )
        async def topology_targets_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                all_services = []
                all_failed = []
                for b in backends:
                    try:
                        topology = await self.prometheus_service.get_service_topology(b.id)
                        all_services.extend([s.model_dump() for s in topology.services])
                    except Exception:
                        pass
                    try:
                        failed = await self.prometheus_service.get_failed_targets(b.id)
                        all_failed.extend([f.model_dump() for f in failed.failed_targets])
                    except Exception:
                        pass
                return json.dumps(
                    {
                        "services": all_services,
                        "failed_targets": all_failed,
                        "total_services": len(all_services),
                        "total_failed_targets": len(all_failed),
                    },
                    default=str,
                    indent=2,
                )
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get target topology: {e}")
