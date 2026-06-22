"""Alerting expression generator tool.

Provides ``tempo_generate_alerting_expression`` — generates PromQL alerting
expressions from trace patterns using Tempo's knowledge of services and
spanmetrics. Does NOT create PrometheusRule CRDs — that's the Prometheus
MCP server's job.

Cross-MCP workflow:
  tempo_generate_alerting_expression → generates PromQL + YAML snippet
  → AI agent passes to prom_upsert_rule_group (Prometheus MCP server)
"""

from typing import Any, Dict, Optional

import yaml
from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions.custom import (
    TempoOperationError,
    TempoQueryError,
    TempoConnectionError,
    TempoValidationError,
)
from tempo_mcp_server.tools.base import BaseTool

_VALID_ALERT_TYPES = {"error_rate", "latency_p99", "throughput_drop"}

# PromQL expression templates keyed by alert_type
_PROMQL_TEMPLATES = {
    "error_rate": (
        'sum(rate(traces_spanmetrics_calls_total{{service="{service}",'
        'status_code="STATUS_CODE_ERROR"}}[{window}])) / '
        'sum(rate(traces_spanmetrics_calls_total{{service="{service}"}}[{window}])) '
        "> {threshold}"
    ),
    "latency_p99": (
        "histogram_quantile(0.99, sum(rate("
        'traces_spanmetrics_duration_milliseconds_bucket{{service="{service}"}}'
        "[{window}])) by (le)) > {threshold}"
    ),
    "throughput_drop": (
        'sum(rate(traces_spanmetrics_calls_total{{service="{service}"}}'
        "[{window}])) < {threshold}"
    ),
}

# TraceQL query templates for annotations
_TRACEQL_TEMPLATES = {
    "error_rate": '{{ resource.service.name = "{service}" && status = error }}',
    "latency_p99": '{{ resource.service.name = "{service}" && duration > {threshold}ms }}',
    "throughput_drop": '{{ resource.service.name = "{service}" }}',
}


class AlertingTools(BaseTool):
    """Alerting expression generation tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        tempo_service = self.tempo_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Generate Alerting Expression from Traces",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_generate_alerting_expression(
            backend_id: str = Field(
                ..., min_length=1, description="Tempo backend ID"
            ),
            service: str = Field(
                ...,
                min_length=1,
                description="Service name to build the alert for",
            ),
            alert_type: str = Field(
                default="error_rate",
                description=(
                    "Alert type: 'error_rate' (errors/total > threshold), "
                    "'latency_p99' (p99 duration > threshold_ms), "
                    "'throughput_drop' (rate drops below threshold_rps)"
                ),
            ),
            threshold: float = Field(
                default=0.05,
                description=(
                    "Threshold value. Meaning depends on alert_type: "
                    "ratio for error_rate (0.05 = 5%), "
                    "ms for latency_p99, rps for throughput_drop"
                ),
            ),
            for_duration: str = Field(
                default="5m",
                description="How long condition must hold before firing",
            ),
            severity: str = Field(
                default="warning",
                description="Alert severity: 'critical', 'warning', 'info'",
            ),
            window: str = Field(
                default="5m",
                description="Rate calculation window (e.g. '5m', '15m')",
            ),
            tenant: Optional[str] = Field(
                default=None,
                description="Tenant ID for multi-tenant backends",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate a PromQL alerting expression from trace patterns.

            Uses Tempo's knowledge of service topology and TraceQL metrics
            to generate the correct PromQL expression that references
            trace-derived metrics (spanmetrics). Read-only — does NOT
            create any CRDs.

            **Cross-server workflow**: Pass the yaml_snippet output to
            the Prometheus MCP server's prom_upsert_rule_group tool to
            apply the alerting rule.

            Returns:
            - {"alert_name": str, "promql_expr": str, "yaml_snippet": str,
               "next_step": str, "validation": {...}}

            When NOT to use: For creating/applying PrometheusRule CRDs,
            use prom_upsert_rule_group in the Prometheus MCP server.

            Prerequisites: Spanmetrics connector must be enabled in the
            upstream OTel Collector to generate traces_spanmetrics_*
            metrics.

            Common errors:
            - Service not found: Verify the service name via
              tempo_get_attribute_values.
            - No spanmetrics: Ensure OTel Collector has a spanmetrics
              connector enabled.
            """
            try:
                if ctx:
                    await ctx.info(
                        f"Generating {alert_type} alert for service '{service}'..."
                    )
                if alert_type not in _VALID_ALERT_TYPES:
                    raise TempoValidationError(
                        f"Invalid alert_type: '{alert_type}'. "
                        f"Supported: {sorted(_VALID_ALERT_TYPES)}"
                    )

                if threshold <= 0:
                    raise TempoValidationError(
                        "Threshold must be a positive number."
                    )

                # Generate alert name
                safe_service = service.replace("-", "_").replace(".", "_")
                alert_name_map = {
                    "error_rate": f"HighErrorRate_{safe_service}",
                    "latency_p99": f"HighLatencyP99_{safe_service}",
                    "throughput_drop": f"ThroughputDrop_{safe_service}",
                }
                alert_name = alert_name_map[alert_type]

                # Generate PromQL expression
                promql_expr = _PROMQL_TEMPLATES[alert_type].format(
                    service=service,
                    window=window,
                    threshold=threshold,
                )

                # Generate TraceQL query for annotations
                traceql_query = _TRACEQL_TEMPLATES[alert_type].format(
                    service=service,
                    threshold=int(threshold) if alert_type == "latency_p99" else threshold,
                )

                # Build description
                description_map = {
                    "error_rate": (
                        f"Error rate for service '{service}' exceeds "
                        f"{threshold * 100:.1f}% over {window}"
                    ),
                    "latency_p99": (
                        f"P99 latency for service '{service}' exceeds "
                        f"{threshold}ms over {window}"
                    ),
                    "throughput_drop": (
                        f"Throughput for service '{service}' dropped below "
                        f"{threshold} req/s over {window}"
                    ),
                }
                description = description_map[alert_type]

                # Build PrometheusRule YAML snippet
                rule_group = {
                    "apiVersion": "monitoring.coreos.com/v1",
                    "kind": "PrometheusRule",
                    "metadata": {
                        "name": f"tempo-alert-{safe_service}",
                        "labels": {
                            "app.kubernetes.io/managed-by": "talkops-mcp",
                            "talkops.ai/alert-source": "tempo",
                        },
                    },
                    "spec": {
                        "groups": [
                            {
                                "name": f"tempo-{safe_service}-alerts",
                                "rules": [
                                    {
                                        "alert": alert_name,
                                        "expr": promql_expr,
                                        "for": for_duration,
                                        "labels": {
                                            "severity": severity,
                                            "source": "tempo",
                                            "service": service,
                                        },
                                        "annotations": {
                                            "summary": description,
                                            "tempo_query": traceql_query,
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                }
                yaml_snippet = yaml.dump(
                    rule_group, default_flow_style=False, sort_keys=False
                )

                # Validate service exists in Tempo
                # B-01: Use scoped attribute `resource.service.name` — the
                # Tempo v2 tag-values API requires scoped TraceQL identifiers.
                # Unscoped `service.name` returns HTTP 400.
                service_exists = False
                validation_warning = None
                try:
                    values_resp = await tempo_service.get_attribute_values(
                        backend_id=backend_id,
                        attribute="resource.service.name",
                        tenant=tenant,
                    )
                    tag_values = values_resp.get("tagValues", [])
                    existing_services = [
                        tv.get("value", "") for tv in tag_values
                    ]
                    service_exists = service in existing_services
                    if not service_exists and existing_services:
                        validation_warning = (
                            f"Service '{service}' not found in Tempo. "
                            f"Known services: {existing_services[:10]}. "
                            "Verify the service name via tempo_get_attribute_values "
                            "with attribute='resource.service.name'."
                        )
                except (TempoQueryError, TempoConnectionError) as e:
                    validation_warning = (
                        f"Service validation could not be completed: {e}. "
                        "The alerting expression was generated but the service "
                        "existence could not be confirmed."
                    )
                except Exception as e:
                    validation_warning = (
                        f"Unexpected error during service validation: {e}. "
                        "The alerting expression was generated but the service "
                        "existence could not be confirmed."
                    )

                result = {
                    "alert_name": alert_name,
                    "alert_type": alert_type,
                    "service": service,
                    "promql_expr": promql_expr,
                    "for_duration": for_duration,
                    "severity": severity,
                    "labels": {
                        "severity": severity,
                        "source": "tempo",
                        "service": service,
                    },
                    "annotations": {
                        "summary": description,
                        "tempo_query": traceql_query,
                    },
                    "yaml_snippet": yaml_snippet,
                    "next_step": (
                        "Pass the yaml_snippet to prom_upsert_rule_group "
                        "in the Prometheus MCP server to create the "
                        "PrometheusRule CRD."
                    ),
                    "validation": {
                        "service_exists": service_exists,
                        "warning": validation_warning,
                    },
                }
                return result

            except (TempoValidationError, TempoOperationError):
                raise
            except Exception as e:
                raise TempoOperationError(
                    f"Failed to generate alerting expression: {e}"
                )
