"""Prometheus TSDB FinOps optimization tools.

Provides granular tools for cardinality reduction, recording rules,
relabeling configs, and remote-write configuration generation.
"""

from typing import Any, Dict, List, Optional

import yaml
from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.json_coerce import coerce_dict, coerce_list


class TsdbFinOpsTools(BaseTool):
    """TSDB FinOps and cardinality optimization tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        prometheus_service = self.prometheus_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Plan Relabel Config",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_plan_relabel(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            metric_name: Optional[str] = Field(
                default=None, description="Metric name to drop or relabel"
            ),
            labels_to_drop: Optional[List[str]] = Field(
                default=None, description="Labels to drop via relabeling"
            ),
            labels_to_keep: Optional[List[str]] = Field(
                default=None, description="Labels to keep, dropping all others"
            ),
            regex_filter: Optional[str] = Field(
                default=None, description="Regex filter for metric name matching"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate metric_relabel_configs YAML to drop/keep labels.

            Use this for FinOps workflows to reduce storage costs by dropping
            high-cardinality labels or unnecessary metrics. Read-only — generates
            config YAML only, does NOT apply changes.

            Returns:
            - {\"relabel_configs\": [...], \"yaml\": str, \"notes\": str}

            When NOT to use: For raw TSDB diagnostics, use the
            prom://tsdb/cardinality resource.
            For full cardinality optimization, use prom_optimize_cardinality.
            """
            try:
                drop_labels = coerce_list(labels_to_drop)
                keep_labels = coerce_list(labels_to_keep)

                configs: List[Dict[str, Any]] = []

                # Case 1: Drop entire metric
                if metric_name and not drop_labels and not keep_labels:
                    filter_regex = regex_filter or metric_name
                    configs.append({
                        "source_labels": ["__name__"],
                        "regex": filter_regex,
                        "action": "drop",
                    })

                # Case 2: Drop specific labels
                if drop_labels:
                    for label in drop_labels:
                        configs.append({
                            "regex": label,
                            "action": "labeldrop",
                        })

                # Case 3: Keep only specific labels
                if keep_labels:
                    configs.append({
                        "regex": "|".join(keep_labels),
                        "action": "labelkeep",
                    })

                config_yaml = yaml.dump(
                    {"metric_relabel_configs": configs},
                    default_flow_style=False,
                )

                return {
                    "relabel_configs": configs,
                    "yaml": config_yaml,
                    "notes": "Add to scrape_configs[].metric_relabel_configs in prometheus.yml",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Relabel plan failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Optimize High Cardinality",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_optimize_cardinality(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            metric_name: Optional[str] = Field(
                default=None, description="Specific metric to analyze"
            ),
            top_n: int = Field(
                default=10, description="Number of top cardinality metrics to analyze"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Analyze top-N cardinality metrics and recommend optimization strategies.

            Use this for FinOps workflows: reducing storage costs via relabeling,
            recording rules, or metric aggregation. Read-only.

            Returns:
            - {\"recommendations\": [{\"metric\": str, \"series_count\": int,
              \"severity\": str, \"strategy\": str}, ...], \"yaml\": str}

            When NOT to use: For raw TSDB diagnostics, use the
            prom://tsdb/cardinality resource.
            For generating relabel configs, use prom_plan_relabel.
            """
            try:
                summary = await prometheus_service.get_cardinality_summary(backend_id)
                recommendations = []

                if metric_name:
                    # Specific metric analysis
                    for m in summary.top_cardinality_metrics:
                        if m.metric_name == metric_name:
                            pct = (m.series_count / max(summary.overview.total_series, 1)) * 100
                            severity = "critical" if pct > 10 else "high" if pct > 5 else "medium"
                            recommendations.append({
                                "metric": m.metric_name,
                                "series_count": m.series_count,
                                "percentage_of_total": round(pct, 2),
                                "severity": severity,
                                "strategies": [
                                    "Drop high-cardinality labels via prom_plan_relabel",
                                    "Create recording rule to pre-aggregate via prom_create_recording_rule",
                                    "Drop metric entirely if unused",
                                ],
                            })
                else:
                    # General top-N analysis
                    for m in summary.top_cardinality_metrics[:top_n]:
                        pct = (m.series_count / max(summary.overview.total_series, 1)) * 100
                        severity = "critical" if pct > 10 else "high" if pct > 5 else "medium"
                        recommendations.append({
                            "metric": m.metric_name,
                            "series_count": m.series_count,
                            "percentage_of_total": round(pct, 2),
                            "severity": severity,
                            "strategies": [
                                "Drop high-cardinality labels via prom_plan_relabel",
                                "Create recording rule via prom_create_recording_rule",
                            ],
                        })

                return {
                    "overview": summary.overview.model_dump(),
                    "recommendations": recommendations,
                    "notes": f"Analyzed top {top_n} metrics by cardinality",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Cardinality optimization failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Create Recording Rule",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_create_recording_rule(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            rule_name: str = Field(
                ..., description="Recording rule name (e.g. 'job:http_requests:rate5m')"
            ),
            rule_expr: str = Field(
                ..., description="PromQL expression for the recording rule"
            ),
            rule_labels: Optional[Dict[str, str]] = Field(
                default=None, description="Additional labels for the recording rule"
            ),
            rule_interval: Optional[str] = Field(
                default=None, description="Evaluation interval (e.g. '1m', '5m')"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate recording rule group YAML.

            Use this to pre-compute expensive PromQL queries as recording rules
            for faster dashboards. Read-only — generates YAML only.

            Returns:
            - {\"rule_group\": {...}, \"yaml\": str, \"notes\": str}

            When NOT to use: For managing live rule groups on Prometheus,
            use prom_upsert_rule_group instead.
            """
            try:
                extra_labels = coerce_dict(rule_labels) or {}

                rule: Dict[str, Any] = {
                    "record": rule_name,
                    "expr": rule_expr,
                }
                if extra_labels:
                    rule["labels"] = extra_labels

                group = {
                    "name": f"mcp_generated_{rule_name}",
                    "rules": [rule],
                }
                if rule_interval:
                    group["interval"] = rule_interval

                config_yaml = yaml.dump(
                    {"groups": [group]},
                    default_flow_style=False,
                )

                return {
                    "rule_group": group,
                    "yaml": config_yaml,
                    "notes": "Save to a rules file and reload Prometheus, or apply via prom_upsert_rule_group",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Recording rule creation failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Configure Remote Write",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_configure_remote_write(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            remote_url: str = Field(
                ..., description="Remote write target URL"
            ),
            remote_name: Optional[str] = Field(
                default=None, description="Remote write config name"
            ),
            write_relabel_configs: Optional[List[Dict[str, Any]]] = Field(
                default=None, description="Write relabel configs to filter what gets sent"
            ),
            queue_config: Optional[Dict[str, Any]] = Field(
                default=None, description="Queue config overrides (capacity, max_shards, etc.)"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate remote_write config YAML for long-term storage.

            Use this to configure remote-write to Thanos, Mimir, or Cortex.
            Read-only — generates config YAML only.

            Returns:
            - {\"remote_write_config\": {...}, \"yaml\": str, \"notes\": str}

            When NOT to use: For raw TSDB diagnostics, use the
            prom://tsdb/cardinality resource.
            """
            try:
                relabel_cfgs = coerce_list(write_relabel_configs)
                q_config = coerce_dict(queue_config)

                rw_config: Dict[str, Any] = {"url": remote_url}
                if remote_name:
                    rw_config["name"] = remote_name
                if relabel_cfgs:
                    rw_config["write_relabel_configs"] = relabel_cfgs
                if q_config:
                    rw_config["queue_config"] = q_config

                config_yaml = yaml.dump(
                    {"remote_write": [rw_config]},
                    default_flow_style=False,
                )

                return {
                    "remote_write_config": rw_config,
                    "yaml": config_yaml,
                    "notes": "Add to prometheus.yml under remote_write section",
                }
            except Exception as e:
                raise PrometheusOperationError(f"Remote write config failed: {e}")
