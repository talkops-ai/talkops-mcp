"""Kubernetes CRD resources for Prometheus MCP server."""

import json
from typing import Any, Dict, List

from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource
from prometheus_mcp_server.services.kubernetes_service import KubernetesService


class KubernetesResources(BaseResource):
    """Kubernetes CRD MCP resources.

    Exposes Kubernetes-native metadata (PrometheusRule CRDs) that cannot
    be discovered through the Prometheus HTTP API alone. This bridges
    the gap between rule discovery (prom://rules/groups) and rule
    mutation (prom_upsert_rule_group with storage_mode: k8s_crd).
    """

    def __init__(self, service_locator: Dict[str, Any]):
        super().__init__(service_locator)
        self.kubernetes_service: KubernetesService = service_locator.get("kubernetes_service")  # type: ignore[assignment]

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://kubernetes/prometheusrules",
            name="prom_kubernetes_prometheusrules",
            description=(
                "Snapshot of all PrometheusRule CRDs across the cluster, "
                "exposing Kubernetes metadata (name, namespace, labels) "
                "required for safe rule upsert operations via prom_upsert_rule_group"
            ),
            mime_type="application/json",
        )
        async def prometheus_rules_resource() -> str:
            try:
                if self.kubernetes_service is None:
                    return json.dumps({
                        "error": "Kubernetes service not configured",
                        "hint": "Set K8S_ENABLED=true in your environment",
                    })

                raw = await self.kubernetes_service.list_prometheus_rules()
                items = raw.get("items", [])

                rules: List[Dict[str, Any]] = []
                for item in items:
                    metadata = item.get("metadata", {})
                    spec = item.get("spec", {})

                    # Extract group summaries with rule counts
                    group_summaries = []
                    total_alert_rules = 0
                    total_recording_rules = 0
                    for group in spec.get("groups", []):
                        alert_count = 0
                        recording_count = 0
                        for rule in group.get("rules", []):
                            if "alert" in rule:
                                alert_count += 1
                            elif "record" in rule:
                                recording_count += 1
                        total_alert_rules += alert_count
                        total_recording_rules += recording_count
                        group_summaries.append({
                            "name": group.get("name", ""),
                            "interval": group.get("interval"),
                            "alert_rules": alert_count,
                            "recording_rules": recording_count,
                            "total_rules": alert_count + recording_count,
                        })

                    rules.append({
                        "name": metadata.get("name", ""),
                        "namespace": metadata.get("namespace", ""),
                        "labels": metadata.get("labels", {}),
                        "annotations": metadata.get("annotations", {}),
                        "groups": group_summaries,
                        "total_groups": len(group_summaries),
                        "total_alert_rules": total_alert_rules,
                        "total_recording_rules": total_recording_rules,
                    })

                return json.dumps({
                    "prometheus_rules": rules,
                    "total_crds": len(rules),
                    "total_groups": sum(r["total_groups"] for r in rules),
                    "total_alert_rules": sum(r["total_alert_rules"] for r in rules),
                    "total_recording_rules": sum(r["total_recording_rules"] for r in rules),
                }, default=str, indent=2)

            except Exception as e:
                raise PrometheusResourceError(
                    f"Failed to list PrometheusRule CRDs: {e}"
                )
