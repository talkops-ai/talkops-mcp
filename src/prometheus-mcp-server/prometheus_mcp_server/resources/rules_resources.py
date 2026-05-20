"""Prometheus rule groups resource."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource


class RulesResources(BaseResource):
    """Rule groups MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://rules/groups",
            name="prom_rule_groups",
            description="Snapshot of all alerting and recording rule groups across backends",
            mime_type="application/json",
        )
        async def rule_groups_resource() -> str:
            try:
                backends = self.prometheus_service.list_backends()
                all_groups = {}
                for b in backends:
                    try:
                        rules_data = await self.prometheus_service.list_rule_groups(b.id)
                        groups = rules_data.get("groups", [])

                        total_alert = 0
                        total_recording = 0
                        for group in groups:
                            for rule in group.get("rules", []):
                                if "alert" in rule:
                                    total_alert += 1
                                elif "record" in rule:
                                    total_recording += 1

                        all_groups[b.id] = {
                            "groups": groups,
                            "total_groups": len(groups),
                            "total_alert_rules": total_alert,
                            "total_recording_rules": total_recording,
                        }
                    except Exception:
                        all_groups[b.id] = {"error": "Failed to fetch rules"}
                return json.dumps(all_groups, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get rule groups: {e}")

        @mcp_instance.resource(
            "prom://schema/label_values",
            name="prom_label_values",
            description="Per-metric label values snapshot for understanding metric dimensionality",
            mime_type="application/json",
        )
        async def label_values_resource() -> str:
            try:
                # Return label topology for a few key metrics
                backends = self.prometheus_service.list_backends()
                results = {}
                for b in backends:
                    try:
                        catalog = await self.prometheus_service.get_metric_catalog(b.id)
                        # Get labels for top 5 metrics only to avoid expensive queries
                        top_metrics = catalog.metrics[:5] if catalog.metrics else []
                        labels = {}
                        for m in top_metrics:
                            try:
                                topology = await self.prometheus_service.explore_label_topology(
                                    b.id, m.name
                                )
                                labels[m.name] = topology.label_values
                            except Exception:
                                continue
                        results[b.id] = labels
                    except Exception:
                        results[b.id] = {"error": "Failed to fetch label values"}
                return json.dumps(results, default=str, indent=2)
            except Exception as e:
                raise PrometheusResourceError(f"Failed to get label values: {e}")
