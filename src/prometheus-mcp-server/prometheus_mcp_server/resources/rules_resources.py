"""Prometheus rule groups resources."""

import json
from prometheus_mcp_server.exceptions import (
    PrometheusResourceError,
    PrometheusResourceNotFoundError,
)
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
                                if "alert" in rule or rule.get("type") == "alerting":
                                    total_alert += 1
                                elif "record" in rule or rule.get("type") == "recording":
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
            "prom://rules/{backend_id}/groups/{group_name}",
            name="prom_rule_group_detail",
            description="Full definition and evaluation health of a specific rule group by backend_id and group_name",
            mime_type="application/json",
        )
        async def rule_group_detail_resource(backend_id: str, group_name: str) -> str:
            try:
                group = await self.prometheus_service.get_rule_group(backend_id, group_name)
                if not group:
                    raise PrometheusResourceNotFoundError(
                        f"Rule group '{group_name}' not found on backend '{backend_id}'. "
                        "Read prom://rules/groups to inspect available group names."
                    )
                return json.dumps(
                    {
                        "backend_id": backend_id,
                        "group": group,
                    },
                    default=str,
                    indent=2,
                )
            except PrometheusResourceNotFoundError:
                raise
            except Exception as e:
                raise PrometheusResourceError(
                    f"Failed to get rule group '{group_name}' on '{backend_id}': {e}"
                )
