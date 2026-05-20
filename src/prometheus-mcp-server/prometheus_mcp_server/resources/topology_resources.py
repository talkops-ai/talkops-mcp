"""Prometheus topology resources (services and failed targets)."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource


class TopologyResources(BaseResource):
    """Topology-related MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://topology/services",
            name="prom_services",
            description="Logical service catalog derived from scrape targets with health status",
            mime_type="application/json",
        )
        async def services_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                all_services = []
                for b in backends:
                    try:
                        topology = await self.prometheus_service.get_service_topology(b.id)
                        all_services.extend([s.model_dump() for s in topology.services])
                    except Exception:
                        continue
                return json.dumps({"services": all_services}, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get service topology: {e}")

        @mcp_instance.resource(
            "prom://topology/failed_targets",
            name="prom_failed_targets",
            description="Aggregated view of failed/down scrape targets for quick triage",
            mime_type="application/json",
        )
        async def failed_targets_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                all_failed = []
                for b in backends:
                    try:
                        failed = await self.prometheus_service.get_failed_targets(b.id)
                        all_failed.extend([f.model_dump() for f in failed.failed_targets])
                    except Exception:
                        continue
                return json.dumps({"failed_targets": all_failed}, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get failed targets: {e}")

        @mcp_instance.resource(
            "prom://topology/services/{job}/metrics",
            name="prom_service_metrics",
            description="Metrics emitted by a specific service/job, with type and HELP text",
            mime_type="application/json",
        )
        async def service_metrics_resource(job: str) -> str:
            try:
                backends = self.prometheus_service.list_backends()
                if not backends:
                    return json.dumps({"error": "No backends configured"})
                # Use the first/default backend
                backend_id = backends[0].id
                result = await self.prometheus_service.get_service_metrics(backend_id, job)
                return json.dumps(result.model_dump(), default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(
                    f"Failed to get metrics for job '{job}': {e}"
                )
