"""Diagnostics & TSDB Cardinality MCP tools (`diagnostics` toolset)."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from mcp.types import ToolAnnotations
from pydantic import BeforeValidator, Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.param_coercion import coerce_json_value


class DiagnosticsTools(BaseTool):
    """Diagnostics and TSDB cardinality analysis tools (`diagnostics` toolset)."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register("diagnostics", is_write=False):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Prometheus & TSDB Diagnostics",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_get_diagnostics(
            backend_id: str = Field(
                default="default",
                description="Prometheus backend ID (see prom://system/backends)",
            ),
            include: Annotated[
                Union[
                    Literal["overview", "targets", "tsdb", "flags", "all"],
                    List[Literal["overview", "targets", "tsdb", "flags", "all"]],
                ],
                BeforeValidator(coerce_json_value),
            ] = Field(
                default="overview",
                description="Diagnostic sections: overview, targets, tsdb, flags, or all (accepts string or list)",
            ),
            scrape_pool: Optional[str] = Field(
                default=None,
                description="Optional job / scrapePool filter for target diagnostics",
            ),
            detail: Literal["summary", "full"] = Field(
                default="summary",
                description="Response detail level ('summary' returns condensed 5-field items)",
            ),
        ) -> Dict[str, Any]:
            """Collect unified backend health, runtime info, WAL replay, TSDB stats, and target health.

            Use when starting an incident investigation or checking Prometheus health. Read-only.

            Returns:
            - {"backend_id": str, "health": str, "version": str, "observations": [...], ...}
            """
            try:
                caps = await self.prometheus_service.get_backend_capabilities(backend_id)
                observations: List[Dict[str, Any]] = []

                health = caps.backend.health
                if health != "healthy":
                    observations.append(
                        {
                            "code": "BACKEND_UNHEALTHY",
                            "backend_id": backend_id,
                            "health": health,
                        }
                    )

                out: Dict[str, Any] = {
                    "backend_id": backend_id,
                    "health": health,
                    "version": caps.backend.version,
                    "type": caps.backend.type,
                    "runtime": caps.runtimeinfo,
                }

                inc_set = (
                    {s.strip().lower() for s in include if isinstance(s, str)}
                    if isinstance(include, list)
                    else {str(include).strip().lower()}
                )

                if inc_set & {"overview", "targets", "all"}:
                    targets_data = await self.prometheus_service.get_targets(backend_id)
                    active_targets = targets_data.get("activeTargets", [])
                    if scrape_pool:
                        active_targets = [
                            t
                            for t in active_targets
                            if t.get("scrapePool") == scrape_pool
                            or t.get("labels", {}).get("job") == scrape_pool
                        ]
                    up_count = sum(1 for t in active_targets if t.get("health") == "up")
                    down_targets = [
                        {
                            "job": t.get("labels", {}).get("job", "unknown"),
                            "instance": t.get("labels", {}).get("instance", "unknown"),
                            "health": t.get("health", "down"),
                            "last_error": t.get("lastError", ""),
                            "scrape_pool": t.get("scrapePool", ""),
                        }
                        for t in active_targets
                        if t.get("health") != "up"
                    ]
                    if down_targets:
                        observations.append(
                            {
                                "code": "TARGETS_DOWN",
                                "down_count": len(down_targets),
                                "affected_jobs": sorted(
                                    {d["job"] for d in down_targets}
                                ),
                            }
                        )
                    out["targets_summary"] = {
                        "total_active": len(active_targets),
                        "up_count": up_count,
                        "down_count": len(down_targets),
                        "down_targets": down_targets[:20]
                        if detail == "summary"
                        else down_targets,
                        "resource_uri": "prom://topology/targets",
                    }

                if inc_set & {"overview", "tsdb", "all"}:
                    try:
                        tsdb = await self.prometheus_service.get_tsdb_status(backend_id)
                        head = tsdb.get("headStats", {})
                        num_series = int(head.get("numSeries", 0))
                        if num_series >= 1_000_000:
                            observations.append(
                                {
                                    "code": "HIGH_HEAD_SERIES",
                                    "num_series": num_series,
                                }
                            )
                        out["tsdb_head"] = {
                            "num_series": num_series,
                            "num_label_pairs": head.get("numLabelPairs", 0),
                            "chunk_count": head.get("chunkCount", 0),
                            "min_time": head.get("minTime"),
                            "max_time": head.get("maxTime"),
                        }
                    except Exception:
                        out["tsdb_head"] = {}

                    wal = await self.prometheus_service.get_wal_replay(backend_id)
                    if wal:
                        out["wal_replay"] = wal

                if inc_set & {"flags", "all"}:
                    flags = await self.prometheus_service.get_flags(backend_id)
                    out["flags"] = flags

                out["observations"] = observations
                return out
            except ValueError as e:
                raise PrometheusOperationError(
                    f"{e} Read resource prom://system/backends to see valid backend_id values."
                )
            except Exception as e:
                raise PrometheusOperationError(f"Failed to collect diagnostics: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Analyze TSDB Cardinality & Series Fan-Out",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_analyze_cardinality(
            backend_id: str = Field(
                default="default",
                description="Prometheus backend ID",
            ),
            metric_prefix: Optional[str] = Field(
                default=None,
                description="Optional metric name prefix filter (e.g. 'http_', 'container_')",
            ),
            focus_label: Optional[str] = Field(
                default=None,
                description="Optional label name to inspect for high fan-out (e.g. 'user_id', 'pod')",
            ),
            top_n: int = Field(
                default=15,
                ge=1,
                le=50,
                description="Number of top high-cardinality metrics/labels to return (1-50)",
            ),
            check_unused_rules: bool = Field(
                default=True,
                description="Check whether top high-cardinality metrics are referenced in any recording/alerting rule",
            ),
        ) -> Dict[str, Any]:
            """Analyze TSDB series cardinality, label value fan-out, and rule usage shares.

            Use when investigating TSDB memory pressure, high series churn, or FinOps cost drivers. Read-only.

            Returns:
            - {"backend_id": str, "overview": {...}, "top_metrics": [...], "top_labels": [...], "observations": [...]}
            """
            try:
                tsdb = await self.prometheus_service.get_tsdb_status(backend_id)
                head = tsdb.get("headStats", {})
                total_series = max(1, int(head.get("numSeries", 0)))

                series_by_metric = tsdb.get("seriesCountByMetricName", [])
                if metric_prefix:
                    series_by_metric = [
                        m
                        for m in series_by_metric
                        if str(m.get("name", "")).startswith(metric_prefix)
                    ]

                rule_expr_blob = ""
                if check_unused_rules:
                    try:
                        rules_data = await self.prometheus_service.list_rule_groups(
                            backend_id
                        )
                        exprs: List[str] = []
                        for grp in rules_data.get("groups", []):
                            for r in grp.get("rules", []):
                                exprs.append(str(r.get("expr", "") or r.get("query", "")))
                        rule_expr_blob = "\n".join(exprs)
                    except Exception:
                        rule_expr_blob = ""

                observations: List[Dict[str, Any]] = []
                top_metrics: List[Dict[str, Any]] = []

                for item in series_by_metric[:top_n]:
                    name = str(item.get("name", ""))
                    count = int(item.get("value", 0))
                    pct_of_total = round((count / total_series) * 100.0, 2)
                    used_in_rules = bool(rule_expr_blob and name in rule_expr_blob)
                    base_name = name[:-7] if name.endswith("_bucket") else name
                    if not used_in_rules and rule_expr_blob and base_name in rule_expr_blob:
                        used_in_rules = True

                    top_metrics.append(
                        {
                            "metric_name": name,
                            "series_count": count,
                            "pct_of_total": pct_of_total,
                            "referenced_in_rules": used_in_rules,
                            "is_histogram_bucket": name.endswith("_bucket"),
                        }
                    )

                    if count >= 10_000 or pct_of_total >= 15.0:
                        observations.append(
                            {
                                "code": "HIGH_CARDINALITY_METRIC",
                                "metric_name": name,
                                "series_count": count,
                                "pct_of_total": pct_of_total,
                            }
                        )
                    if name.endswith("_bucket") and count >= 5_000:
                        observations.append(
                            {
                                "code": "HISTOGRAM_BUCKET_EXPLOSION",
                                "metric_name": name,
                                "series_count": count,
                            }
                        )
                    if check_unused_rules and rule_expr_blob and not used_in_rules and count >= 5_000:
                        observations.append(
                            {
                                "code": "UNREFERENCED_HIGH_COST_METRIC",
                                "metric_name": name,
                                "series_count": count,
                            }
                        )

                label_counts = tsdb.get("labelValueCountByLabelName", [])
                top_labels: List[Dict[str, Any]] = []
                for lbl in label_counts[:top_n]:
                    lname = str(lbl.get("name", ""))
                    lval_count = int(lbl.get("value", 0))
                    top_labels.append(
                        {
                            "label_name": lname,
                            "unique_values": lval_count,
                        }
                    )
                    if lname != "__name__" and lval_count >= 1_000:
                        observations.append(
                            {
                                "code": "UNBOUNDED_LABEL_FANOUT",
                                "label_name": lname,
                                "unique_values": lval_count,
                            }
                        )

                focus_label_details: Optional[Dict[str, Any]] = None
                if focus_label:
                    matching_pairs = [
                        p
                        for p in tsdb.get("seriesCountByLabelValuePair", [])
                        if str(p.get("name", "")).startswith(f"{focus_label}=")
                    ]
                    focus_label_details = {
                        "label_name": focus_label,
                        "top_value_pairs": matching_pairs[:top_n],
                    }

                return {
                    "backend_id": backend_id,
                    "overview": {
                        "total_series": int(head.get("numSeries", 0)),
                        "num_label_pairs": int(head.get("numLabelPairs", 0)),
                        "chunk_count": int(head.get("chunkCount", 0)),
                        "estimated_memory_bytes": int(head.get("chunkCount", 0)) * 128,
                    },
                    "top_metrics": top_metrics,
                    "top_labels": top_labels,
                    "focus_label_details": focus_label_details,
                    "observations": observations,
                    "resource_uri": "prom://tsdb/cardinality",
                }
            except ValueError as e:
                raise PrometheusOperationError(
                    f"{e} Read resource prom://system/backends to see valid backend_id values."
                )
            except Exception as e:
                raise PrometheusOperationError(f"Failed to analyze cardinality: {e}")
