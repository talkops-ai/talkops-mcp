"""Alert authoring helper tools.

Provides granular tools for drafting alert rules from natural
language intent and tuning existing rules based on firing history.
"""

import time
from typing import Any, Dict, List, Optional

import yaml
from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool


# Common alert templates for best-practice rule drafting
_ALERT_TEMPLATES = {
    "high_error_rate": {
        "expr_template": 'sum(rate({metric}[5m])) by (job) / sum(rate({total_metric}[5m])) by (job) > {threshold}',
        "default_for": "5m",
        "default_severity": "critical",
        "summary_template": "High error rate detected for {{ $labels.job }}",
        "description_template": "Error rate is {{ $value | humanizePercentage }} for {{ $labels.job }}",
    },
    "high_latency": {
        "expr_template": 'histogram_quantile({quantile}, sum(rate({metric}[5m])) by (le, job)) > {threshold}',
        "default_for": "10m",
        "default_severity": "warning",
        "summary_template": "High latency detected for {{ $labels.job }}",
        "description_template": "P{quantile_pct} latency is {{ $value }}s for {{ $labels.job }}",
    },
    "instance_down": {
        "expr_template": 'up{{job="{job}"}} == 0',
        "default_for": "5m",
        "default_severity": "critical",
        "summary_template": "Instance {{ $labels.instance }} is down",
        "description_template": "{{ $labels.instance }} of job {{ $labels.job }} has been down for more than 5 minutes",
    },
    "disk_space": {
        "expr_template": '(node_filesystem_avail_bytes{{mountpoint="/"}} / node_filesystem_size_bytes{{mountpoint="/"}}) * 100 < {threshold}',
        "default_for": "15m",
        "default_severity": "warning",
        "summary_template": "Low disk space on {{ $labels.instance }}",
        "description_template": "Disk space is {{ $value }}% on {{ $labels.instance }}",
    },
    "high_cpu": {
        "expr_template": '100 - (avg by (instance) (rate(node_cpu_seconds_total{{mode="idle"}}[5m])) * 100) > {threshold}',
        "default_for": "10m",
        "default_severity": "warning",
        "summary_template": "High CPU usage on {{ $labels.instance }}",
        "description_template": "CPU usage is {{ $value }}% on {{ $labels.instance }}",
    },
    "high_memory": {
        "expr_template": '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > {threshold}',
        "default_for": "10m",
        "default_severity": "warning",
        "summary_template": "High memory usage on {{ $labels.instance }}",
        "description_template": "Memory usage is {{ $value }}% on {{ $labels.instance }}",
    },
    "pod_restart": {
        "expr_template": 'increase(kube_pod_container_status_restarts_total[1h]) > {threshold}',
        "default_for": "0m",
        "default_severity": "warning",
        "summary_template": "Pod {{ $labels.pod }} restarting frequently",
        "description_template": "Pod {{ $labels.pod }} has restarted {{ $value }} times in the last hour",
    },
    "generic_threshold": {
        "expr_template": '{metric} {operator} {threshold}',
        "default_for": "5m",
        "default_severity": "warning",
        "summary_template": "{metric} threshold exceeded",
        "description_template": "{metric} is {{ $value }} (threshold: {threshold})",
    },
}


class AuthoringTools(BaseTool):
    """Alert authoring helper tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        prometheus_service = self.prometheus_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Draft Alert Rule",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_draft_alert_rule(
            intent: str = Field(
                ..., description="Natural language description of what to alert on (e.g. 'alert when error rate exceeds 5%')"
            ),
            metric: Optional[str] = Field(
                default=None, description="Primary metric name (e.g. 'http_requests_total')"
            ),
            threshold: Optional[float] = Field(
                default=None, description="Threshold value for the alert"
            ),
            severity: Optional[str] = Field(
                default=None, description="Alert severity: critical, warning, info"
            ),
            for_duration: Optional[str] = Field(
                default=None, description="For duration (e.g. '5m', '10m')"
            ),
            template: Optional[str] = Field(
                default=None,
                description="Template to use: high_error_rate, high_latency, instance_down, disk_space, high_cpu, high_memory, pod_restart, generic_threshold"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate an alert rule from natural language intent.

            Use this to draft a Prometheus alerting rule based on a description
            of what you want to monitor. Returns ready-to-use YAML. Read-only.

            Returns:
            - {\"alert_name\": str, \"rule_group_yaml\": str, \"expr\": str,
               \"for_duration\": str, \"severity\": str, \"rationale\": str}

            When NOT to use: For applying rules to Prometheus, use
            prom_upsert_rule_group after drafting.
            """
            try:
                # Determine template from intent
                template_name = template
                if not template_name:
                    intent_lower = intent.lower()
                    if any(w in intent_lower for w in ["error", "failure", "fail"]):
                        template_name = "high_error_rate"
                    elif any(w in intent_lower for w in ["latency", "slow", "response time"]):
                        template_name = "high_latency"
                    elif any(w in intent_lower for w in ["down", "unreachable", "unavailable"]):
                        template_name = "instance_down"
                    elif any(w in intent_lower for w in ["disk", "storage", "filesystem"]):
                        template_name = "disk_space"
                    elif any(w in intent_lower for w in ["cpu", "processor"]):
                        template_name = "high_cpu"
                    elif any(w in intent_lower for w in ["memory", "ram", "oom"]):
                        template_name = "high_memory"
                    elif any(w in intent_lower for w in ["restart", "crash", "crashloop"]):
                        template_name = "pod_restart"
                    else:
                        template_name = "generic_threshold"

                tmpl = _ALERT_TEMPLATES.get(template_name, _ALERT_TEMPLATES["generic_threshold"])

                # Build expression
                expr = tmpl["expr_template"]
                effective_threshold = threshold or 0.05
                effective_metric = metric or "http_requests_total"

                expr = expr.replace("{metric}", effective_metric)
                expr = expr.replace("{threshold}", str(effective_threshold))
                expr = expr.replace("{operator}", ">")
                expr = expr.replace("{total_metric}", effective_metric.replace("_errors_", "_requests_").replace("_failed_", "_"))
                expr = expr.replace("{quantile}", "0.95")
                expr = expr.replace("{quantile_pct}", "95")
                expr = expr.replace("{job}", effective_metric.split("{")[0] if "{" in effective_metric else "")

                # Build alert name
                alert_name = f"{template_name}_{effective_metric}".replace(".", "_")
                if len(alert_name) > 60:
                    alert_name = alert_name[:60]

                effective_for = for_duration or tmpl["default_for"]
                effective_severity = severity or tmpl["default_severity"]

                # Build summary and description
                summary = tmpl["summary_template"].replace("{metric}", effective_metric)
                description = tmpl["description_template"].replace(
                    "{metric}", effective_metric
                ).replace("{threshold}", str(effective_threshold))

                # Build rule group YAML
                rule = {
                    "alert": alert_name,
                    "expr": expr,
                    "for": effective_for,
                    "labels": {"severity": effective_severity},
                    "annotations": {
                        "summary": summary,
                        "description": description,
                    },
                }

                group = {
                    "groups": [{
                        "name": f"mcp_drafted_{alert_name}",
                        "rules": [rule],
                    }],
                }

                rule_yaml = yaml.dump(group, default_flow_style=False)

                return {
                    "alert_name": alert_name,
                    "rule_group_yaml": rule_yaml,
                    "expr": expr,
                    "for_duration": effective_for,
                    "severity": effective_severity,
                    "template_used": template_name,
                    "rationale": (
                        f"Generated from template '{template_name}' based on intent: '{intent}'. "
                        f"Validate with prom_check_rule_group before applying."
                    ),
                    "next_steps": [
                        "Validate: Use prom_check_rule_group with the generated YAML",
                        "Test: Use prom_simulate_firing_historical to verify behavior",
                        "Apply: Use prom_upsert_rule_group to deploy",
                    ],
                }
            except Exception as e:
                raise PrometheusOperationError(f"Alert drafting failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Tune Alert Rule",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_tune_alert_rule(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            alert_name: str = Field(
                ..., description="Alert name to tune"
            ),
            current_expr: Optional[str] = Field(
                default=None, description="Current PromQL expression"
            ),
            current_for: Optional[str] = Field(
                default=None, description="Current 'for' duration"
            ),
            current_threshold: Optional[float] = Field(
                default=None, description="Current threshold value"
            ),
            lookback_hours: int = Field(
                default=24, description="Hours to analyze (default: 24)"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Suggest rule adjustments based on firing history.

            Analyzes the alert's recent firing pattern and recommends
            threshold/for adjustments to reduce noise. Read-only.

            Returns:
            - {\"alert_name\": str, \"current_config\": {...},
               \"firing_stats\": {...}, \"recommendations\": [{...}]}

            When NOT to use: For drafting new rules, use prom_draft_alert_rule.
            """
            try:
                now = time.time()
                start = now - (lookback_hours * 3600)

                # Get firing history
                series = await prometheus_service.get_alerts_for_state(
                    backend_id, alert_name, start, now, "5m"
                )

                # Analyze firing pattern
                firing_durations: List[float] = []
                for s in series:
                    values = s.get("values", [])
                    fire_start: Optional[float] = None
                    for ts, val in values:
                        ts_f = float(ts)
                        val_f = float(val) if isinstance(val, (int, float, str)) else 0
                        if val_f > 0 and fire_start is None:
                            fire_start = ts_f
                        elif val_f == 0 and fire_start is not None:
                            firing_durations.append(ts_f - fire_start)
                            fire_start = None
                    if fire_start is not None:
                        firing_durations.append(now - fire_start)

                total_firings = len(firing_durations)
                avg_dur = sum(firing_durations) / total_firings if total_firings else 0
                freq_per_day = total_firings / (lookback_hours / 24) if lookback_hours > 0 else 0

                recommendations = []

                # Noisy alert recommendations
                if freq_per_day > 10:
                    recommendations.append({
                        "type": "increase_for_duration",
                        "rationale": f"Alert fires {freq_per_day:.1f} times/day. Increasing 'for' will reduce flapping.",
                        "suggested_for": "10m" if (current_for or "5m") == "5m" else "15m",
                    })

                if total_firings > 0 and avg_dur < 120:
                    recommendations.append({
                        "type": "increase_for_duration",
                        "rationale": f"Average firing duration is short ({avg_dur:.0f}s). Consider longer 'for'.",
                        "suggested_for": "10m",
                    })

                if total_firings == 0:
                    recommendations.append({
                        "type": "lower_threshold",
                        "rationale": "Alert never fired. Threshold may be too conservative.",
                        "current_threshold": current_threshold,
                        "suggested_action": "Review if the threshold matches actual traffic patterns.",
                    })

                if not recommendations:
                    recommendations.append({
                        "type": "no_change",
                        "rationale": "Alert firing pattern looks healthy. No tuning needed.",
                    })

                return {
                    "alert_name": alert_name,
                    "lookback_hours": lookback_hours,
                    "current_config": {
                        "expr": current_expr,
                        "for": current_for,
                        "threshold": current_threshold,
                    },
                    "firing_stats": {
                        "total_firings": total_firings,
                        "avg_duration_seconds": round(avg_dur, 2),
                        "frequency_per_day": round(freq_per_day, 2),
                    },
                    "recommendations": recommendations,
                }
            except Exception as e:
                raise PrometheusOperationError(f"Alert tuning failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Suggest PromQL",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_suggest_promql(
            intent: str = Field(
                ..., description="Natural language description of what to query (e.g. 'CPU usage per pod')"
            ),
            metric_hints: Optional[List[str]] = Field(
                default=None,
                description="Optional metric name hints to guide the suggestion"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate a PromQL expression from natural language intent.

            Use this to help users write PromQL queries when they know what
            they want but not the syntax. Pure helper — read-only, no API calls.

            Returns:
            - {\"query\": str, \"explanation\": str, \"alternatives\": [str]}

            When NOT to use: For executing queries, use prom_query_instant
            or prom_query_range after getting a suggestion.
            """
            try:
                hints = coerce_list(metric_hints) if metric_hints else []
                intent_lower = intent.lower()

                # Pattern matching for common intents
                suggestions = []

                if any(w in intent_lower for w in ["cpu", "processor"]):
                    suggestions.append({
                        "query": '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
                        "explanation": "CPU usage percentage per instance (node_exporter)",
                        "context": "node",
                    })
                    suggestions.append({
                        "query": 'sum(rate(container_cpu_usage_seconds_total[5m])) by (pod)',
                        "explanation": "CPU usage per pod (cAdvisor/kubelet)",
                        "context": "kubernetes",
                    })

                elif any(w in intent_lower for w in ["memory", "ram"]):
                    suggestions.append({
                        "query": '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100',
                        "explanation": "Memory usage percentage per node",
                        "context": "node",
                    })
                    suggestions.append({
                        "query": 'container_memory_working_set_bytes / container_spec_memory_limit_bytes * 100',
                        "explanation": "Memory usage percentage per container",
                        "context": "kubernetes",
                    })

                elif any(w in intent_lower for w in ["request", "http", "traffic"]):
                    metric = hints[0] if hints else "http_requests_total"
                    suggestions.append({
                        "query": f'sum(rate({metric}[5m])) by (job)',
                        "explanation": f"Request rate per job from {metric}",
                    })
                    suggestions.append({
                        "query": f'sum(rate({metric}[5m])) by (status_code)',
                        "explanation": "Request rate broken down by status code",
                    })

                elif any(w in intent_lower for w in ["error", "failure"]):
                    metric = hints[0] if hints else "http_requests_total"
                    suggestions.append({
                        "query": f'sum(rate({metric}{{status=~"5.."}}[5m])) / sum(rate({metric}[5m]))',
                        "explanation": "Error rate (5xx responses / total requests)",
                    })

                elif any(w in intent_lower for w in ["latency", "response time", "duration"]):
                    metric = hints[0] if hints else "http_request_duration_seconds_bucket"
                    suggestions.append({
                        "query": f'histogram_quantile(0.95, sum(rate({metric}[5m])) by (le))',
                        "explanation": "P95 latency from histogram",
                    })
                    suggestions.append({
                        "query": f'histogram_quantile(0.99, sum(rate({metric}[5m])) by (le))',
                        "explanation": "P99 latency from histogram",
                    })

                elif any(w in intent_lower for w in ["disk", "storage", "filesystem"]):
                    suggestions.append({
                        "query": '(node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100',
                        "explanation": "Available disk space percentage",
                    })

                elif any(w in intent_lower for w in ["up", "down", "health"]):
                    suggestions.append({
                        "query": 'up == 0',
                        "explanation": "All targets that are currently down",
                    })
                    suggestions.append({
                        "query": 'count by (job) (up == 0)',
                        "explanation": "Count of down targets per job",
                    })

                else:
                    # Generic: try to use hints
                    if hints:
                        metric = hints[0]
                        suggestions.append({
                            "query": metric,
                            "explanation": f"Raw value of {metric}",
                        })
                        suggestions.append({
                            "query": f'rate({metric}[5m])',
                            "explanation": f"Rate of change of {metric} over 5 minutes",
                        })
                    else:
                        suggestions.append({
                            "query": 'up',
                            "explanation": "Health status of all scrape targets",
                        })

                primary = suggestions[0] if suggestions else {"query": "up", "explanation": "Default: target health"}
                alternatives = [s["query"] for s in suggestions[1:]]

                return {
                    "query": primary["query"],
                    "explanation": primary.get("explanation", ""),
                    "alternatives": alternatives,
                    "notes": "Use prom_validate_promql to check syntax, then prom_query_instant to execute.",
                }
            except Exception as e:
                raise PrometheusOperationError(f"PromQL suggestion failed: {e}")


# Need to import at module level for prom_suggest_promql
from prometheus_mcp_server.utils.json_coerce import coerce_list
