"""Prometheus rules management tools.

Provides granular tools for inspecting, upserting,
deleting, and describing alerting/recording rule groups.

Note: Rule group inventory listing has moved to the
``prom://rules/groups`` resource (v4 refactor).
"""

from typing import Any, Dict, List, Optional

import yaml
from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.json_coerce import coerce_dict, coerce_list


class RulesTools(BaseTool):
    """Alerting and recording rule management tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        prometheus_service = self.prometheus_service
        kubernetes_service = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Rule Group",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_get_rule_group(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            group_name: str = Field(..., description="Rule group name to inspect"),
            file_filter: Optional[str] = Field(
                default=None, description="Filter by file path (for disambiguation)"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get a single rule group by name with full rule details.

            Use this to inspect specific alerting or recording rules within
            a group. Read-only.

            Returns:
            - {\"name\": str, \"file\": str, \"rules\": [...], \"interval\": str}

            When NOT to use: For listing all groups, use the
            prom://rules/groups resource.

            Common errors:
            - Group not found: Verify name via the prom://rules/groups resource.
            """
            try:
                group = await prometheus_service.get_rule_group(
                    backend_id, group_name, file_filter=file_filter
                )
                if not group:
                    raise PrometheusOperationError(
                        f"Rule group '{group_name}' not found. "
                        "Use prom_list_rule_groups to see available groups."
                    )
                return group
            except PrometheusOperationError:
                raise
            except Exception as e:
                raise PrometheusOperationError(f"Failed to get rule group: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Upsert Rule Group",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def prom_upsert_rule_group(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            group_name: str = Field(..., description="Rule group name"),
            rules: List[Dict[str, Any]] = Field(
                ..., description="List of rule definitions (alert or recording rules)"
            ),
            *,
            interval: Optional[str] = Field(
                default=None, description="Evaluation interval (e.g. '1m', '30s')"
            ),
            namespace: Optional[str] = Field(
                default="monitoring", description="Kubernetes namespace for CRD mode"
            ),
            crd_labels: Optional[Dict[str, str]] = Field(
                default=None, description="Optional labels for CRD metadata (e.g. {'release': 'kube-prometheus-stack'})"
            ),
            storage_mode: str = Field(
                default="yaml_output",
                description="Storage mode: 'yaml_output' (returns YAML), 'k8s_crd' (applies PrometheusRule CRD), 'http_ruler' (Mimir/Cortex HTTP API)"
            ),
            ctx: Context,
        ) -> Dict[str, Any]:
            """Create or update a rule group.

            MUTATES STATE depending on storage_mode:
            - 'yaml_output': Generates YAML only (safe, read-only).
            - 'k8s_crd': Applies PrometheusRule CRD to Kubernetes cluster.
            - 'http_ruler': Pushes to Mimir/Cortex/Thanos Ruler HTTP API.

            **WARNING: 'k8s_crd' and 'http_ruler' modes modify external state.**

            Returns:
            - {\"group_name\": str, \"storage_mode\": str, \"yaml\": str,
               \"applied\": bool, \"notes\": str}

            When NOT to use: For generating recording rule YAML without
            applying, use prom_create_recording_rule.

            Prerequisites:
            - k8s_crd: Prometheus Operator must be installed.
            - http_ruler: Backend must support Ruler API.

            Common errors:
            - Invalid rule syntax: Use prom_check_rule_group to validate first.
            """
            try:
                rules_list = coerce_list(rules)

                # Build the rule group
                group = {
                    "name": group_name,
                    "rules": rules_list,
                }
                if interval:
                    group["interval"] = interval

                group_yaml = yaml.dump(
                    {"groups": [group]},
                    default_flow_style=False,
                )

                applied = False
                notes = ""

                if storage_mode == "yaml_output":
                    notes = "YAML generated. Save to a rules file and reload Prometheus."

                elif storage_mode == "k8s_crd":
                    # Build PrometheusRule CRD
                    crd_name = group_name.replace("_", "-").replace(".", "-").lower()
                    
                    extra_labels = coerce_dict(crd_labels) or {}
                    operator_labels = await kubernetes_service.get_rule_required_labels()
                    if operator_labels:
                        extra_labels.update(operator_labels)
                        
                    if not extra_labels:
                        extra_labels = {"prometheus": "kube-prometheus"}

                    crd = {
                        "apiVersion": "monitoring.coreos.com/v1",
                        "kind": "PrometheusRule",
                        "metadata": {
                            "name": crd_name,
                            "namespace": namespace,
                            "labels": extra_labels,
                        },
                        "spec": {
                            "groups": [group],
                        },
                    }
                    try:
                        await kubernetes_service.apply_custom_resource(
                            namespace or "monitoring", crd
                        )
                        applied = True
                        notes = f"PrometheusRule CRD '{crd_name}' applied to {namespace}"
                    except Exception as e:
                        notes = f"CRD apply failed: {e}. YAML is still available."

                elif storage_mode == "http_ruler":
                    # POST to ruler API (Mimir/Cortex)
                    try:
                        from prometheus_mcp_server.services.prometheus_service import ApiError
                        resp = await prometheus_service._request(
                            "POST", backend_id,
                            f"/api/v1/rules/{namespace or 'default'}",
                            content=group_yaml,
                            headers={"Content-Type": "application/yaml"},
                        )
                        applied = True
                        notes = f"Rule group '{group_name}' pushed to HTTP Ruler API"
                    except Exception as e:
                        notes = f"HTTP Ruler push failed: {e}. YAML is still available."

                else:
                    raise PrometheusOperationError(
                        f"Invalid storage_mode: {storage_mode}. "
                        "Must be 'yaml_output', 'k8s_crd', or 'http_ruler'."
                    )

                return {
                    "group_name": group_name,
                    "storage_mode": storage_mode,
                    "yaml": group_yaml,
                    "applied": applied,
                    "notes": notes,
                }
            except PrometheusOperationError:
                raise
            except Exception as e:
                raise PrometheusOperationError(f"Upsert failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Delete Rule Group",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def prom_delete_rule_group(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            group_name: str = Field(..., description="Rule group name to delete"),
            namespace: Optional[str] = Field(
                default="monitoring", description="Kubernetes namespace for CRD mode"
            ),
            storage_mode: str = Field(
                default="k8s_crd",
                description="Storage mode: 'k8s_crd' or 'http_ruler'"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Delete a rule group.

            DESTRUCTIVE — removes alerting/recording rules from the backend.

            **WARNING: This permanently removes rule groups. Alerts using
            these rules will stop firing.**

            Returns:
            - {\"group_name\": str, \"deleted\": bool, \"notes\": str}

            Common errors:
            - Group not found: Verify name via prom_list_rule_groups.
            """
            try:
                deleted = False
                notes = ""
                crd_name = group_name.replace("_", "-").replace(".", "-").lower()

                if storage_mode == "k8s_crd":
                    try:
                        await kubernetes_service.delete_custom_resource(
                            namespace or "monitoring",
                            "monitoring.coreos.com", "v1", "prometheusrules",
                            crd_name,
                        )
                        deleted = True
                        notes = f"PrometheusRule CRD '{crd_name}' deleted from {namespace}"
                    except Exception as e:
                        notes = f"CRD delete failed: {e}"

                elif storage_mode == "http_ruler":
                    try:
                        await prometheus_service._request(
                            "DELETE", backend_id,
                            f"/api/v1/rules/{namespace or 'default'}/{group_name}",
                        )
                        deleted = True
                        notes = f"Rule group '{group_name}' deleted via HTTP Ruler API"
                    except Exception as e:
                        notes = f"HTTP Ruler delete failed: {e}"

                else:
                    raise PrometheusOperationError(
                        f"Invalid storage_mode: {storage_mode}. "
                        "Must be 'k8s_crd' or 'http_ruler'."
                    )

                return {
                    "group_name": group_name,
                    "deleted": deleted,
                    "notes": notes,
                }
            except PrometheusOperationError:
                raise
            except Exception as e:
                raise PrometheusOperationError(f"Delete failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Describe Alert Rule",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_describe_alert_rule(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            group_name: str = Field(..., description="Rule group containing the alert"),
            alert_name: str = Field(..., description="Alert rule name to describe"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Provide a human-readable explanation of an alerting rule.

            Use this to understand what an alert rule does, when it fires,
            and what it means. Read-only.

            Returns:
            - {\"alert_name\": str, \"expr\": str, \"for_duration\": str,
               \"labels\": {...}, \"annotations\": {...}, \"explanation\": str,
               \"state\": str}

            When NOT to use: For listing all rules, use prom_list_rule_groups.
            """
            try:
                group = await prometheus_service.get_rule_group(
                    backend_id, group_name
                )
                if not group:
                    raise PrometheusOperationError(
                        f"Rule group '{group_name}' not found."
                    )

                # Find the specific alert rule
                alert_rule = None
                for rule in group.get("rules", []):
                    if rule.get("alert") == alert_name:
                        alert_rule = rule
                        break

                if not alert_rule:
                    raise PrometheusOperationError(
                        f"Alert rule '{alert_name}' not found in group '{group_name}'."
                    )

                # Build human-readable explanation
                expr = alert_rule.get("query") or alert_rule.get("expr", "")
                for_dur = alert_rule.get("duration") or alert_rule.get("for", "0s")
                labels = alert_rule.get("labels", {})
                annotations = alert_rule.get("annotations", {})
                state = alert_rule.get("state", "unknown")
                severity = labels.get("severity", "unknown")

                explanation_parts = [
                    f"**Alert: {alert_name}**",
                    f"- **Severity**: {severity}",
                    f"- **Expression**: `{expr}`",
                    f"- **For Duration**: {for_dur} (must be true for this long before firing)",
                    f"- **Current State**: {state}",
                ]

                if annotations.get("summary"):
                    explanation_parts.append(f"- **Summary**: {annotations['summary']}")
                if annotations.get("description"):
                    explanation_parts.append(f"- **Description**: {annotations['description']}")
                if annotations.get("runbook_url"):
                    explanation_parts.append(f"- **Runbook**: {annotations['runbook_url']}")

                return {
                    "alert_name": alert_name,
                    "group_name": group_name,
                    "expr": expr,
                    "for_duration": for_dur,
                    "labels": labels,
                    "annotations": annotations,
                    "state": state,
                    "explanation": "\n".join(explanation_parts),
                }
            except PrometheusOperationError:
                raise
            except Exception as e:
                raise PrometheusOperationError(f"Describe failed: {e}")
