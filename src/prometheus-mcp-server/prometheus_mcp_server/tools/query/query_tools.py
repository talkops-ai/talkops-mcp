"""PromQL Query, Exemplar, and Compound Analytical MCP tools (`query` toolset)."""

from __future__ import annotations

import asyncio
import math
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from mcp.types import ToolAnnotations
from pydantic import Field

from prometheus_mcp_server.exceptions import (
    PrometheusOperationError,
    PrometheusQueryError,
    PrometheusValidationError,
)
from prometheus_mcp_server.tools.base import BaseTool, parse_time_param
from prometheus_mcp_server.utils.promql_helpers import (
    compute_auto_step,
    compute_series_stats,
    find_unbounded_metric_selector_error,
    parse_duration_seconds,
)
from prometheus_mcp_server.utils.response_size import enforce_structured_size_limit


_RANGE_WINDOW_RE = re.compile(r"\[[0-9]+[smhdwy]\]")


def _rewrite_query_window(query: str, window: str) -> str:
    """Replace the range vector window selector (e.g. `[5m]`) with `[{window}]`."""
    if "{window}" in query:
        return query.replace("{window}", window)
    if _RANGE_WINDOW_RE.search(query):
        return _RANGE_WINDOW_RE.sub(f"[{window}]", query)
    return query


def _lint_promql_syntax(query: str) -> Tuple[List[str], List[str]]:
    """Lightweight deterministic PromQL syntax and anti-pattern check."""
    errors: List[str] = []
    warnings: List[str] = []
    q = (query or "").strip()
    if not q:
        errors.append("Query cannot be empty.")
        return errors, warnings

    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {")": "(", "]": "[", "}": "{"}
    stack: List[str] = []
    in_str: Optional[str] = None
    escaped = False
    for ch in q:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            continue
        if ch in pairs:
            stack.append(ch)
        elif ch in closing:
            if not stack or stack[-1] != closing[ch]:
                errors.append(f"Unbalanced delimiter '{ch}' in PromQL expression.")
                break
            stack.pop()
    if in_str:
        errors.append(f"Unterminated string literal ({in_str}) in PromQL expression.")
    if stack:
        errors.append(f"Unclosed delimiter(s) {stack} in PromQL expression.")

    unbounded_err = find_unbounded_metric_selector_error(q)
    if unbounded_err:
        errors.append(unbounded_err)
    elif re.search(r'=~\s*"\.\*"', q) or re.search(r'=~\s*"\.\+"', q):
        warnings.append(
            "Avoid broad regex matchers like =~'.*'; use label!=\"\" or exact matchers."
        )
    if (
        "_bucket" in q
        and "histogram_quantile(" in q
        and not re.search(r"\b(?:by|without)\s*\(", q)
    ):
        warnings.append(
            "Classic histogram_quantile() over _bucket series should aggregate with 'sum by (le) (rate(...))'."
        )
    return errors, warnings


def _format_series_key(labels: Dict[str, str]) -> str:
    filtered = {k: v for k, v in sorted(labels.items()) if k != "__name__"}
    if not filtered:
        return labels.get("__name__", "series")
    pairs = ",".join(f'{k}="{v}"' for k, v in filtered.items())
    return f"{{{pairs}}}"


class QueryTools(BaseTool):
    """PromQL discovery, instant/range query, exemplar, and compound SRE analysis tools (`query` toolset)."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register("query", is_write=False):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Explore Prometheus Metrics, Series, and Labels",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_explore_metrics(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            metric_pattern: Optional[str] = Field(
                default=None,
                description="Substring or regex pattern to filter metric names (e.g. 'http_request')",
            ),
            label_name: Optional[str] = Field(
                default=None,
                description="Metric name or label name to inspect label values for",
            ),
            match_selector: Optional[str] = Field(
                default=None,
                description="PromQL series selector for /api/v1/series (e.g. 'up{job=\"prometheus\"}')",
            ),
            job: Optional[str] = Field(
                default=None,
                description="Optional scrape job name to discover metrics emitted specifically by that job via /api/v1/targets/metadata",
            ),
            limit: int = Field(
                default=50,
                ge=1,
                le=200,
                description="Maximum items to return per page (1-200)",
            ),
            cursor: Optional[str] = Field(
                default=None,
                description="Pagination cursor offset from a previous call",
            ),
        ) -> Dict[str, Any]:
            """Discover metric names, types, HELP text, per-job target metrics, label values, or matching series selectors.

            Use before writing PromQL to avoid hallucinating metric or label names. Read-only.

            Returns:
            - {"backend_id": str, "metrics": [...], "series": [...], "label_topology": {...}, "next_cursor": str|None}
            """
            try:
                offset = int(cursor) if cursor and str(cursor).isdigit() else 0
                out: Dict[str, Any] = {"backend_id": backend_id}

                if match_selector:
                    series = await self.prometheus_service.get_series(
                        backend_id, match_selector=match_selector, limit=offset + limit + 1
                    )
                    sliced = series[offset : offset + limit]
                    has_more = len(series) > offset + limit
                    out["series"] = sliced
                    out["total_returned"] = len(sliced)
                    out["next_cursor"] = str(offset + limit) if has_more else None
                    if has_more:
                        out["_truncation_advice"] = (
                            f"Showing {len(sliced)} series from offset {offset}. "
                            f"Pass cursor='{offset + limit}' or narrow match_selector."
                        )
                    return out

                if label_name and not metric_pattern and not job:
                    # Explore label topology for a metric name
                    topology = await self.prometheus_service.explore_label_topology(
                        backend_id, label_name, max_values_per_label=limit
                    )
                    out["label_topology"] = topology.model_dump()
                    return out

                if job and hasattr(self.prometheus_service, "get_service_metrics"):
                    svc_list = await self.prometheus_service.get_service_metrics(
                        backend_id, job
                    )
                    metrics = svc_list.metrics
                    out["job"] = job
                else:
                    catalog = await self.prometheus_service.get_metric_catalog(backend_id)
                    metrics = catalog.metrics

                if metric_pattern:
                    try:
                        rx = re.compile(metric_pattern, re.IGNORECASE)
                        metrics = [
                            m
                            for m in metrics
                            if rx.search(m.name) or (m.help and rx.search(m.help))
                        ]
                    except re.error:
                        pat_lower = metric_pattern.lower()
                        metrics = [
                            m
                            for m in metrics
                            if pat_lower in m.name.lower()
                            or (m.help and pat_lower in m.help.lower())
                        ]

                total_matched = len(metrics)
                sliced_metrics = metrics[offset : offset + limit]
                has_more = total_matched > offset + limit
                out["metrics"] = [
                    {
                        "name": m.name,
                        "type": m.type,
                        "unit": m.unit,
                        "help": m.help,
                    }
                    for m in sliced_metrics
                ]
                out["total_matched"] = total_matched
                out["next_cursor"] = str(offset + limit) if has_more else None
                if has_more:
                    out["_truncation_advice"] = (
                        f"Returned {len(sliced_metrics)} of {total_matched} metrics. "
                        f"Pass cursor='{offset + limit}' or refine metric_pattern."
                    )

                if label_name and sliced_metrics:
                    topology = await self.prometheus_service.explore_label_topology(
                        backend_id, sliced_metrics[0].name, max_values_per_label=limit
                    )
                    out["label_topology"] = topology.model_dump()

                return out
            except ValueError as e:
                raise PrometheusOperationError(
                    f"{e} Read resource prom://system/backends to see valid backend_id values."
                )
            except Exception as e:
                raise PrometheusOperationError(f"Metric exploration failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Execute PromQL Instant Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_query_instant(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            query: str = Field(
                ...,
                min_length=1,
                description="PromQL expression (counters must use rate/irate/increase)",
            ),
            time: Optional[str] = Field(
                default=None,
                description="Evaluation time (RFC3339, Unix seconds, or relative e.g. '-5m'; defaults to now)",
            ),
            timeout: str = Field(
                default="30s",
                description="Evaluation timeout (e.g. '15s', '30s')",
            ),
            limit: int = Field(
                default=50,
                ge=1,
                le=500,
                description="Maximum series to return (1-500)",
            ),
            detail: Literal["summary", "full"] = Field(
                default="summary",
                description="'summary' returns condensed 5-field items; 'full' returns raw samples",
            ),
            validate_only: bool = Field(
                default=False,
                description="When True, validates PromQL syntax and counter-rate safety without executing TSDB query",
            ),
        ) -> Dict[str, Any]:
            """Execute a point-in-time PromQL instant query (or `validate_only=True` preflight check) with semantic counter guardrails.

            Use for current metric values, status checks, topk() rankings, or preflight query linting. Read-only.

            Returns:
            - {"resultType": str, "series_count": int, "series": [...], "eval_time_seconds": float}
            """
            if validate_only:
                errors, warnings = _lint_promql_syntax(query)
                try:
                    await self.prometheus_service.enforce_counter_rule(
                        backend_id, query, allow_raw=False
                    )
                except ValueError as counter_err:
                    errors.append(str(counter_err))
                except Exception:
                    pass
                return {
                    "backend_id": backend_id,
                    "query": query,
                    "validate_only": True,
                    "valid": len(errors) == 0,
                    "errors": errors,
                    "warnings": warnings,
                }

            try:
                unbounded_err = find_unbounded_metric_selector_error(query)
                if unbounded_err:
                    raise PrometheusValidationError(unbounded_err)
                await self.prometheus_service.enforce_counter_rule(
                    backend_id, query, allow_raw=False
                )
                eval_ts = parse_time_param(time, default_ts=None) if time else None
                res = await self.prometheus_service.instant_query(
                    backend_id,
                    query=query,
                    ts=eval_ts,
                    timeout=timeout,
                    max_samples=limit,
                )

                items: List[Dict[str, Any]] = []
                for sample in res.result:
                    ts_val, str_val = sample.value
                    try:
                        num_val: Any = round(float(str_val), 6)
                    except (TypeError, ValueError):
                        num_val = str_val
                    if detail == "summary":
                        items.append(
                            {
                                "metric": sample.metric.get("__name__", ""),
                                "series": _format_series_key(sample.metric),
                                "labels": sample.metric,
                                "value": num_val,
                                "timestamp": ts_val,
                            }
                        )
                    else:
                        items.append(sample.model_dump())

                out: Dict[str, Any] = {
                    "backend_id": backend_id,
                    "query": query,
                    "resultType": res.resultType,
                    "series_count": res.sample_count,
                    "series": items,
                    "eval_time_seconds": round(res.eval_time_seconds, 4),
                    "truncated": res.truncated,
                }
                if res.truncated:
                    out["_truncation_advice"] = (
                        f"Output truncated to {limit} of {res.sample_count} series. "
                        "Use sum(...) by (...) or topk(10, ...) in PromQL to reduce cardinality."
                    )
                soft_limit = getattr(self.config, "response_size_soft_limit", 40_000)
                return enforce_structured_size_limit(
                    out,
                    truncatable_key="series",
                    max_bytes=soft_limit,
                    query_hint=query,
                )
            except ValueError as e:
                raise PrometheusQueryError(str(e))
            except Exception as e:
                raise PrometheusQueryError(
                    f"Instant query failed: {e}. Verify metric/label names via prom_explore_metrics."
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Execute PromQL Range Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_query_range(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            query: str = Field(
                ...,
                min_length=1,
                description="PromQL expression (counters must use rate/irate/increase)",
            ),
            start: str = Field(
                default="-1h",
                description="Range start (RFC3339, Unix epoch, or relative offset like '-1h')",
            ),
            end: str = Field(
                default="now",
                description="Range end (RFC3339, Unix epoch, or 'now')",
            ),
            step: Optional[str] = Field(
                default=None,
                description="Step duration (e.g. '30s', '5m'; auto-computed if omitted)",
            ),
            include_chart: bool = Field(
                default=False,
                description="Include an A2UI time-series chart specification in the response",
            ),
            limit: int = Field(
                default=25,
                ge=1,
                le=200,
                description="Maximum series to return (1-200)",
            ),
            detail: Literal["summary", "full"] = Field(
                default="summary",
                description="'summary' returns pre-computed stats (min/max/avg/p95/latest); 'full' includes raw points",
            ),
        ) -> Dict[str, Any]:
            """Execute a PromQL range query with auto-step sizing, per-series stats, and optional A2UI chart.

            Use for trend analysis, spike detection, and charting over a time window. Read-only.

            Returns:
            - {"series_count": int, "step": str, "series": [{"labels": {...}, "stats": {...}}], "chart": {...}}
            """
            try:
                unbounded_err = find_unbounded_metric_selector_error(query)
                if unbounded_err:
                    raise PrometheusValidationError(unbounded_err)
                await self.prometheus_service.enforce_counter_rule(
                    backend_id, query, allow_raw=False
                )
                end_ts = parse_time_param(end)
                start_ts = parse_time_param(start, default_ts=end_ts - 3600)
                if start_ts >= end_ts:
                    raise PrometheusValidationError(
                        f"start ({start_ts}) must be earlier than end ({end_ts})."
                    )

                effective_step = step or compute_auto_step(start_ts, end_ts, max_points=120)
                res = await self.prometheus_service.range_query(
                    backend_id,
                    query=query,
                    start=start_ts,
                    end=end_ts,
                    step=effective_step,
                    max_points_per_series=120,
                )

                total_series = len(res.series)
                truncated = total_series > limit
                sliced = res.series[:limit]

                formatted_series: List[Dict[str, Any]] = []
                for s in sliced:
                    numeric_pts: List[Tuple[float, float]] = []
                    for ts_val, v_str in s.values:
                        try:
                            numeric_pts.append((float(ts_val), float(v_str)))
                        except (TypeError, ValueError):
                            continue
                    stats = compute_series_stats(numeric_pts)
                    entry: Dict[str, Any] = {
                        "series": _format_series_key(s.metric),
                        "labels": s.metric,
                        "stats": stats,
                    }
                    if detail == "full":
                        entry["values"] = s.values
                    formatted_series.append(entry)

                out: Dict[str, Any] = {
                    "backend_id": backend_id,
                    "query": query,
                    "start": start_ts,
                    "end": end_ts,
                    "step": effective_step,
                    "series_count": total_series,
                    "series": formatted_series,
                    "truncated": truncated,
                }
                if truncated:
                    out["_truncation_advice"] = (
                        f"Showing {limit} of {total_series} series. "
                        "Aggregate with sum/avg/max by (...) or filter labels in PromQL."
                    )
                if include_chart:
                    out["chart"] = {
                        "type": "a2ui_timeseries",
                        "title": query,
                        "start": start_ts,
                        "end": end_ts,
                        "step": effective_step,
                        "series": [
                            {
                                "name": _format_series_key(s.metric),
                                "points": s.values,
                            }
                            for s in sliced[:10]
                        ],
                    }
                soft_limit = getattr(self.config, "response_size_soft_limit", 40_000)
                return enforce_structured_size_limit(
                    out,
                    truncatable_key="series",
                    max_bytes=soft_limit,
                    query_hint=query,
                )
            except (PrometheusValidationError, PrometheusQueryError):
                raise
            except ValueError as e:
                raise PrometheusQueryError(str(e))
            except Exception as e:
                raise PrometheusQueryError(
                    f"Range query failed: {e}. Verify metric/label names via prom_explore_metrics."
                )

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Query Prometheus Trace Exemplars",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_query_exemplars(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            query: str = Field(
                ...,
                min_length=1,
                description="PromQL selector or histogram expression to extract exemplars from",
            ),
            start: str = Field(
                default="-15m",
                description="Start time (RFC3339, Unix epoch, or relative offset e.g. '-15m')",
            ),
            end: str = Field(
                default="now",
                description="End time (RFC3339, Unix epoch, or 'now')",
            ),
            limit: int = Field(
                default=20,
                ge=1,
                le=100,
                description="Maximum exemplars to return, sorted by highest value first (1-100)",
            ),
        ) -> Dict[str, Any]:
            """Fetch OpenTelemetry/Tempo trace exemplars (`trace_id`, `span_id`) attached to metric samples.

            Use to pivot from high-latency histograms or error counters to distributed traces in Tempo. Read-only.

            Returns:
            - {"backend_id": str, "exemplar_count": int, "exemplars": [{"trace_id": str, "span_id": str, "value": float, ...}]}
            """
            try:
                end_ts = parse_time_param(end)
                start_ts = parse_time_param(start, default_ts=end_ts - 900)
                exemplars = await self.prometheus_service.query_exemplars(
                    backend_id,
                    query=query,
                    start=start_ts,
                    end=end_ts,
                    limit=limit,
                )
                trace_ids = [
                    ex["trace_id"] for ex in exemplars if ex.get("trace_id")
                ]
                return {
                    "backend_id": backend_id,
                    "query": query,
                    "start": start_ts,
                    "end": end_ts,
                    "exemplar_count": len(exemplars),
                    "trace_ids": list(dict.fromkeys(trace_ids)),
                    "exemplars": exemplars,
                }
            except Exception as e:
                raise PrometheusQueryError(f"Failed to query exemplars: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Compare PromQL Metric Across Two Time Periods",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_compare_periods(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            query: str = Field(
                ...,
                min_length=1,
                description="PromQL expression to compare between current and baseline windows",
            ),
            current_start: str = Field(
                default="-15m",
                description="Current window start (e.g. '-15m' or RFC3339)",
            ),
            current_end: str = Field(
                default="now",
                description="Current window end (e.g. 'now' or RFC3339)",
            ),
            baseline_offset: str = Field(
                default="1h",
                description="How far back to shift the baseline window (e.g. '1h', '1d', '1w')",
            ),
            step: Optional[str] = Field(
                default=None,
                description="Optional step duration (auto-computed if omitted)",
            ),
        ) -> Dict[str, Any]:
            """Compare a PromQL expression between a current window and a time-shifted baseline window.

            Use during deployment regression or anomaly triage to compute deltas and z-scores server-side. Read-only.

            Returns:
            - {"comparisons": [{"series": str, "current_avg": float, "baseline_avg": float, "pct_change": float, "z_score": float|None, ...}], "observations": [...]}
            """
            try:
                unbounded_err = find_unbounded_metric_selector_error(query)
                if unbounded_err:
                    raise PrometheusValidationError(unbounded_err)
                await self.prometheus_service.enforce_counter_rule(
                    backend_id, query, allow_raw=False
                )
                cur_end = parse_time_param(current_end)
                cur_start = parse_time_param(current_start, default_ts=cur_end - 900)
                offset_secs = parse_duration_seconds(baseline_offset, default=3600.0)
                base_start = cur_start - offset_secs
                base_end = cur_end - offset_secs
                effective_step = step or compute_auto_step(cur_start, cur_end, max_points=60)

                cur_res, base_res = await asyncio.gather(
                    self.prometheus_service.range_query(
                        backend_id, query, cur_start, cur_end, effective_step, max_points_per_series=100
                    ),
                    self.prometheus_service.range_query(
                        backend_id, query, base_start, base_end, effective_step, max_points_per_series=100
                    ),
                )

                cur_map = {
                    _format_series_key(s.metric): (
                        s.metric,
                        [(float(ts), float(v)) for ts, v in s.values if v is not None],
                    )
                    for s in cur_res.series
                }
                base_map = {
                    _format_series_key(s.metric): (
                        s.metric,
                        [(float(ts), float(v)) for ts, v in s.values if v is not None],
                    )
                    for s in base_res.series
                }

                comparisons: List[Dict[str, Any]] = []
                observations: List[Dict[str, Any]] = []

                all_keys = sorted(set(cur_map.keys()) | set(base_map.keys()))
                for key in all_keys[:50]:
                    labels, cur_pts = cur_map.get(key, ({}, []))
                    _, base_pts = base_map.get(key, (labels, []))
                    cur_stats = compute_series_stats(cur_pts)
                    base_stats = compute_series_stats(base_pts)

                    cur_avg = cur_stats["avg"]
                    base_avg = base_stats["avg"]
                    abs_delta: Optional[float] = None
                    pct_change: Optional[float] = None
                    base_stddev: Optional[float] = None
                    z_score: Optional[float] = None

                    if base_avg is not None and len(base_pts) >= 2:
                        variance = sum((v - base_avg) ** 2 for _, v in base_pts) / len(base_pts)
                        base_stddev = round(math.sqrt(variance), 6)

                    if cur_avg is not None and base_avg is not None:
                        abs_delta = round(cur_avg - base_avg, 6)
                        if base_stddev is not None and base_stddev > 0:
                            z_score = round((cur_avg - base_avg) / base_stddev, 3)
                        if base_avg != 0:
                            pct_change = round(((cur_avg - base_avg) / abs(base_avg)) * 100.0, 2)
                            if pct_change >= 50.0:
                                observations.append(
                                    {
                                        "code": "SIGNIFICANT_SPIKE",
                                        "series": key,
                                        "pct_change": pct_change,
                                        "z_score": z_score,
                                    }
                                )
                            elif pct_change <= -50.0:
                                observations.append(
                                    {
                                        "code": "SIGNIFICANT_DROP",
                                        "series": key,
                                        "pct_change": pct_change,
                                        "z_score": z_score,
                                    }
                                )
                        if z_score is not None and abs(z_score) >= 3.0 and (
                            pct_change is None or abs(pct_change) < 50.0
                        ):
                            observations.append(
                                {
                                    "code": "Z_SCORE_ANOMALY",
                                    "series": key,
                                    "z_score": z_score,
                                }
                            )
                    elif cur_avg is not None and base_avg is None:
                        observations.append({"code": "NEW_SERIES_APPEARED", "series": key})

                    if (z_score is not None and abs(z_score) >= 3.0) or (
                        pct_change is not None and abs(pct_change) >= 50.0
                    ):
                        anomaly_status = "SIGNIFICANT_ANOMALY"
                    elif (z_score is not None and abs(z_score) >= 2.0) or (
                        pct_change is not None and abs(pct_change) >= 25.0
                    ):
                        anomaly_status = "ELEVATED_DRIFT"
                    else:
                        anomaly_status = "NORMAL"

                    comparisons.append(
                        {
                            "series": key,
                            "labels": labels,
                            "current_avg": cur_avg,
                            "baseline_avg": base_avg,
                            "baseline_stddev": base_stddev,
                            "abs_delta": abs_delta,
                            "pct_change": pct_change,
                            "z_score": z_score,
                            "anomaly_status": anomaly_status,
                            "current_p95": cur_stats["p95"],
                            "baseline_p95": base_stats["p95"],
                        }
                    )

                out_cmp = {
                    "backend_id": backend_id,
                    "query": query,
                    "current_window": {"start": cur_start, "end": cur_end},
                    "baseline_window": {"start": base_start, "end": base_end, "offset": baseline_offset},
                    "comparisons": comparisons,
                    "observations": observations,
                }
                soft_limit = getattr(self.config, "response_size_soft_limit", 40_000)
                return enforce_structured_size_limit(
                    out_cmp,
                    truncatable_key="comparisons",
                    max_bytes=soft_limit,
                    query_hint=query,
                )
            except ValueError as e:
                raise PrometheusQueryError(str(e))
            except Exception as e:
                raise PrometheusQueryError(f"Period comparison failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Analyze Service RED Golden Signals",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_analyze_service_red(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            service_selector: str = Field(
                ...,
                min_length=1,
                description="Service/job label selector (e.g. 'job=\"api-server\"' or 'service=\"checkout\"')",
            ),
            lookback: str = Field(
                default="15m",
                description="Lookback window for RED evaluation (e.g. '5m', '15m', '1h')",
            ),
            metric_convention: Literal[
                "auto",
                "prometheus_http",
                "prometheus_native",
                "otel",
                "otel_utf8",
                "otel_rpc",
                "spanmetrics",
                "istio",
                "grpc",
            ] = Field(
                default="auto",
                description="Metric naming convention: auto, prometheus_http, prometheus_native (Prometheus 3.0 Native Histograms), otel, otel_utf8 (Prometheus 3.0 UTF-8 OTel), otel_rpc, spanmetrics, istio, or grpc",
            ),
            include_exemplars: bool = Field(
                default=True,
                description="Fetch trace exemplars for latency/error spikes if available",
            ),
        ) -> Dict[str, Any]:
            """Compute RED golden signals (Request Rate, Error Ratio, p50/p95/p99 Duration) supporting classic and Prometheus 3.0 Native Histograms plus trace exemplars.

            Use as the primary service triage tool to avoid running multiple separate PromQL queries. Read-only.

            Returns:
            - {"service_selector": str, "request_rate_rps": float, "error_ratio_pct": float, "latency_seconds": {"p50": ..., "p95": ..., "p99": ...}, "exemplars": [...], "observations": [...]}
            """
            try:
                sel = service_selector.strip().strip("{}")
                conventions = (
                    [
                        "prometheus_http",
                        "prometheus_native",
                        "otel",
                        "otel_utf8",
                        "spanmetrics",
                        "otel_rpc",
                        "istio",
                        "grpc",
                    ]
                    if metric_convention == "auto"
                    else [metric_convention]
                )

                rate_val: Optional[float] = None
                err_ratio_pct: Optional[float] = None
                p50_val: Optional[float] = None
                p95_val: Optional[float] = None
                p99_val: Optional[float] = None
                used_convention = conventions[0]
                histogram_format = "classic"
                exemplars: List[Dict[str, Any]] = []

                def _extract_scalar(res: Any) -> Optional[float]:
                    if isinstance(res, Exception) or not getattr(res, "result", None):
                        return None
                    try:
                        v = float(res.result[0].value[1])
                        return round(v, 6) if math.isfinite(v) else None
                    except (TypeError, ValueError, IndexError):
                        return None

                for conv in conventions:
                    if conv == "prometheus_http":
                        req_q = f"sum(rate(http_requests_total{{{sel}}}[{lookback}]))"
                        err_q = f"sum(rate(http_requests_total{{{sel},status=~\"5..\"}}[{lookback}])) / clamp_min(sum(rate(http_requests_total{{{sel}}}[{lookback}])), 1e-9) * 100"
                        p50_q = f"histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        p95_q = f"histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        p99_q = f"histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        ex_q = f"http_request_duration_seconds_bucket{{{sel}}}"
                        cur_hist_fmt = "classic"
                    elif conv == "prometheus_native":
                        req_q = f"sum(rate(http_requests_total{{{sel}}}[{lookback}]))"
                        err_q = f"sum(rate(http_requests_total{{{sel},status=~\"5..\"}}[{lookback}])) / clamp_min(sum(rate(http_requests_total{{{sel}}}[{lookback}])), 1e-9) * 100"
                        p50_q = f"histogram_quantile(0.50, sum(rate(http_request_duration_seconds{{{sel}}}[{lookback}])))"
                        p95_q = f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds{{{sel}}}[{lookback}])))"
                        p99_q = f"histogram_quantile(0.99, sum(rate(http_request_duration_seconds{{{sel}}}[{lookback}])))"
                        ex_q = f"http_request_duration_seconds{{{sel}}}"
                        cur_hist_fmt = "native"
                    elif conv == "otel":
                        req_q = f"sum(rate(http_server_request_duration_seconds_count{{{sel}}}[{lookback}]))"
                        err_q = f"sum(rate(http_server_request_duration_seconds_count{{{sel},http_response_status_code=~\"5..\"}}[{lookback}])) / clamp_min(sum(rate(http_server_request_duration_seconds_count{{{sel}}}[{lookback}])), 1e-9) * 100"
                        p50_q = f"histogram_quantile(0.50, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        p95_q = f"histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        p99_q = f"histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        ex_q = f"http_server_request_duration_seconds_bucket{{{sel}}}"
                        cur_hist_fmt = "classic"
                    elif conv == "otel_utf8":
                        req_q = f'sum(histogram_count(rate({{"http.server.request.duration",{sel}}}[{lookback}])))'
                        err_q = f'sum(histogram_count(rate({{"http.server.request.duration",{sel},"http.response.status_code"=~"5.."}}[{lookback}]))) / clamp_min(sum(histogram_count(rate({{"http.server.request.duration",{sel}}}[{lookback}]))), 1e-9) * 100'
                        p50_q = f'histogram_quantile(0.50, sum(rate({{"http.server.request.duration",{sel}}}[{lookback}])))'
                        p95_q = f'histogram_quantile(0.95, sum(rate({{"http.server.request.duration",{sel}}}[{lookback}])))'
                        p99_q = f'histogram_quantile(0.99, sum(rate({{"http.server.request.duration",{sel}}}[{lookback}])))'
                        ex_q = f'{{"http.server.request.duration",{sel}}}'
                        cur_hist_fmt = "native_utf8"
                    elif conv == "spanmetrics":
                        req_q = f"sum(rate(traces_spanmetrics_calls_total{{{sel}}}[{lookback}]))"
                        err_q = f"sum(rate(traces_spanmetrics_calls_total{{{sel},status_code=\"STATUS_CODE_ERROR\"}}[{lookback}])) / clamp_min(sum(rate(traces_spanmetrics_calls_total{{{sel}}}[{lookback}])), 1e-9) * 100"
                        p50_q = f"histogram_quantile(0.50, sum by (le) (rate(traces_spanmetrics_latency_bucket{{{sel}}}[{lookback}])))"
                        p95_q = f"histogram_quantile(0.95, sum by (le) (rate(traces_spanmetrics_latency_bucket{{{sel}}}[{lookback}])))"
                        p99_q = f"histogram_quantile(0.99, sum by (le) (rate(traces_spanmetrics_latency_bucket{{{sel}}}[{lookback}])))"
                        ex_q = f"traces_spanmetrics_latency_bucket{{{sel}}}"
                        cur_hist_fmt = "classic"
                    elif conv == "otel_rpc":
                        req_q = f"sum(rate(rpc_server_requests_total{{{sel}}}[{lookback}]))"
                        err_q = f"sum(rate(rpc_server_errors_total{{{sel}}}[{lookback}])) / clamp_min(sum(rate(rpc_server_requests_total{{{sel}}}[{lookback}])), 1e-9) * 100"
                        p50_q = f"histogram_quantile(0.50, sum by (le) (rate(rpc_server_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        p95_q = f"histogram_quantile(0.95, sum by (le) (rate(rpc_server_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        p99_q = f"histogram_quantile(0.99, sum by (le) (rate(rpc_server_duration_seconds_bucket{{{sel}}}[{lookback}])))"
                        ex_q = f"rpc_server_duration_seconds_bucket{{{sel}}}"
                        cur_hist_fmt = "classic"
                    elif conv == "istio":
                        req_q = f"sum(rate(istio_requests_total{{{sel}}}[{lookback}]))"
                        err_q = f"sum(rate(istio_requests_total{{{sel},response_code=~\"5..\"}}[{lookback}])) / clamp_min(sum(rate(istio_requests_total{{{sel}}}[{lookback}])), 1e-9) * 100"
                        p50_q = f"histogram_quantile(0.50, sum by (le) (rate(istio_request_duration_milliseconds_bucket{{{sel}}}[{lookback}]))) / 1000"
                        p95_q = f"histogram_quantile(0.95, sum by (le) (rate(istio_request_duration_milliseconds_bucket{{{sel}}}[{lookback}]))) / 1000"
                        p99_q = f"histogram_quantile(0.99, sum by (le) (rate(istio_request_duration_milliseconds_bucket{{{sel}}}[{lookback}]))) / 1000"
                        ex_q = f"istio_request_duration_milliseconds_bucket{{{sel}}}"
                        cur_hist_fmt = "classic"
                    else:  # grpc
                        req_q = f"sum(rate(grpc_server_handled_total{{{sel}}}[{lookback}]))"
                        err_q = f"sum(rate(grpc_server_handled_total{{{sel},grpc_code!=\"OK\"}}[{lookback}])) / clamp_min(sum(rate(grpc_server_handled_total{{{sel}}}[{lookback}])), 1e-9) * 100"
                        p50_q = f"histogram_quantile(0.50, sum by (le) (rate(grpc_server_handling_seconds_bucket{{{sel}}}[{lookback}])))"
                        p95_q = f"histogram_quantile(0.95, sum by (le) (rate(grpc_server_handling_seconds_bucket{{{sel}}}[{lookback}])))"
                        p99_q = f"histogram_quantile(0.99, sum by (le) (rate(grpc_server_handling_seconds_bucket{{{sel}}}[{lookback}])))"
                        ex_q = f"grpc_server_handling_seconds_bucket{{{sel}}}"
                        cur_hist_fmt = "classic"

                    r_res, e_res, l50_res, l95_res, l99_res = await asyncio.gather(
                        self.prometheus_service.instant_query(backend_id, req_q),
                        self.prometheus_service.instant_query(backend_id, err_q),
                        self.prometheus_service.instant_query(backend_id, p50_q),
                        self.prometheus_service.instant_query(backend_id, p95_q),
                        self.prometheus_service.instant_query(backend_id, p99_q),
                        return_exceptions=True,
                    )

                    rate_val = _extract_scalar(r_res)
                    err_ratio_pct = _extract_scalar(e_res)
                    p50_val = _extract_scalar(l50_res)
                    p95_val = _extract_scalar(l95_res)
                    p99_val = _extract_scalar(l99_res)

                    # If classic counter matched (rate_val is not None) but _bucket returned None,
                    # check if the latency histogram is a Prometheus 3.0 Native Histogram!
                    if (
                        conv in ("prometheus_http", "otel")
                        and rate_val is not None
                        and p95_val is None
                    ):
                        nh_metric = (
                            "http_request_duration_seconds"
                            if conv == "prometheus_http"
                            else "http_server_request_duration_seconds"
                        )
                        nh50_res, nh95_res, nh99_res = await asyncio.gather(
                            self.prometheus_service.instant_query(
                                backend_id,
                                f"histogram_quantile(0.50, sum(rate({nh_metric}{{{sel}}}[{lookback}])))",
                            ),
                            self.prometheus_service.instant_query(
                                backend_id,
                                f"histogram_quantile(0.95, sum(rate({nh_metric}{{{sel}}}[{lookback}])))",
                            ),
                            self.prometheus_service.instant_query(
                                backend_id,
                                f"histogram_quantile(0.99, sum(rate({nh_metric}{{{sel}}}[{lookback}])))",
                            ),
                            return_exceptions=True,
                        )
                        nh95 = _extract_scalar(nh95_res)
                        if nh95 is not None:
                            p50_val = _extract_scalar(nh50_res)
                            p95_val = nh95
                            p99_val = _extract_scalar(nh99_res)
                            ex_q = f"{nh_metric}{{{sel}}}"
                            cur_hist_fmt = "native"

                    if any(x is not None for x in (rate_val, err_ratio_pct, p95_val)):
                        used_convention = conv
                        histogram_format = cur_hist_fmt
                        if include_exemplars:
                            now_ts = parse_time_param("now")
                            start_ts = now_ts - parse_duration_seconds(lookback, 900.0)
                            try:
                                exemplars = await self.prometheus_service.query_exemplars(
                                    backend_id, ex_q, start_ts, now_ts, limit=10
                                )
                            except Exception:
                                exemplars = []
                        break

                observations: List[Dict[str, Any]] = []
                if err_ratio_pct is not None and err_ratio_pct >= 1.0:
                    observations.append(
                        {"code": "ELEVATED_ERROR_RATIO", "error_ratio_pct": err_ratio_pct}
                    )
                if p99_val is not None and p50_val is not None and p50_val > 0 and (p99_val / p50_val) >= 5.0:
                    observations.append(
                        {
                            "code": "HIGH_TAIL_LATENCY_SKEW",
                            "p50_seconds": p50_val,
                            "p99_seconds": p99_val,
                        }
                    )

                return {
                    "backend_id": backend_id,
                    "service_selector": service_selector,
                    "lookback": lookback,
                    "metric_convention": used_convention,
                    "histogram_format": histogram_format,
                    "request_rate_rps": rate_val,
                    "error_ratio_pct": err_ratio_pct,
                    "latency_seconds": {
                        "p50": p50_val,
                        "p95": p95_val,
                        "p99": p99_val,
                    },
                    "exemplars": exemplars,
                    "observations": observations,
                }
            except Exception as e:
                raise PrometheusQueryError(f"Service RED analysis failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Evaluate Multi-Window SLO Error Budget Burn",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_evaluate_slo_burn(
            backend_id: str = Field(
                ...,
                min_length=1,
                description="Prometheus backend ID (e.g. 'default')",
            ),
            error_query: str = Field(
                ...,
                min_length=1,
                description="PromQL rate expression for bad/error events (e.g. 'sum(rate(http_requests_total{job=\"api\",status=~\"5..\"}[5m]))')",
            ),
            total_query: str = Field(
                ...,
                min_length=1,
                description="PromQL rate expression for total valid events (e.g. 'sum(rate(http_requests_total{job=\"api\"}[5m]))')",
            ),
            slo_target: float = Field(
                default=0.999,
                gt=0.5,
                lt=1.0,
                description="Target SLO objective between 0.5 and 1.0 (e.g. 0.999 for 99.9%)",
            ),
            window_days: int = Field(
                default=30,
                ge=1,
                le=90,
                description="SLO compliance period in days (default: 30)",
            ),
        ) -> Dict[str, Any]:
            """Evaluate Google SRE multi-window multi-burn-rate error budget consumption (1h/5m, 6h/30m, 24h/2h, 72h/6h) in one call.

            Computes error ratio, burn rate multiplier, and remaining budget across short/long burn windows. Read-only.

            Returns:
            - {"slo_target": float, "error_budget_fraction": float, "burn_rate_multiplier": float, "multi_window_tiers": [...], "estimated_exhaustion_hours": float|None, "observations": [...]}
            """
            try:
                error_budget = 1.0 - slo_target

                def _extract_rate(res: Any) -> float:
                    if isinstance(res, Exception) or not getattr(res, "result", None):
                        return 0.0
                    try:
                        v = float(res.result[0].value[1])
                        return v if math.isfinite(v) and v >= 0 else 0.0
                    except (TypeError, ValueError, IndexError):
                        return 0.0

                err_res, tot_res = await asyncio.gather(
                    self.prometheus_service.instant_query(backend_id, error_query),
                    self.prometheus_service.instant_query(backend_id, total_query),
                )

                err_rate = _extract_rate(err_res)
                tot_rate = _extract_rate(tot_res)

                current_error_ratio = (err_rate / tot_rate) if tot_rate > 0 else 0.0
                burn_rate = (
                    round(current_error_ratio / error_budget, 3)
                    if error_budget > 0
                    else 0.0
                )
                total_window_hours = window_days * 24.0
                exhaustion_hours = (
                    round(total_window_hours / burn_rate, 2)
                    if burn_rate > 0
                    else None
                )

                # Evaluate Google SRE Multi-Window Multi-Burn-Rate tiers (1h/5m, 6h/30m, 24h/2h, 72h/6h)
                sre_windows = ["5m", "30m", "1h", "2h", "6h", "24h", "72h"]
                has_rewritable_window = bool(
                    _RANGE_WINDOW_RE.search(error_query) or "{window}" in error_query
                )
                window_burn_map: Dict[str, Dict[str, float]] = {}

                if has_rewritable_window:
                    win_tasks = []
                    for w in sre_windows:
                        win_tasks.append(
                            self.prometheus_service.instant_query(
                                backend_id, _rewrite_query_window(error_query, w)
                            )
                        )
                        win_tasks.append(
                            self.prometheus_service.instant_query(
                                backend_id, _rewrite_query_window(total_query, w)
                            )
                        )
                    win_results = await asyncio.gather(*win_tasks, return_exceptions=True)
                    for idx, w in enumerate(sre_windows):
                        w_err = _extract_rate(win_results[idx * 2])
                        w_tot = _extract_rate(win_results[idx * 2 + 1])
                        w_ratio = (w_err / w_tot) if w_tot > 0 else 0.0
                        w_burn = (
                            round(w_ratio / error_budget, 3)
                            if error_budget > 0
                            else 0.0
                        )
                        window_burn_map[w] = {
                            "error_rate": round(w_err, 6),
                            "total_rate": round(w_tot, 6),
                            "error_ratio": round(w_ratio, 6),
                            "burn_rate": w_burn,
                        }
                else:
                    for w in sre_windows:
                        window_burn_map[w] = {
                            "error_rate": round(err_rate, 6),
                            "total_rate": round(tot_rate, 6),
                            "error_ratio": round(current_error_ratio, 6),
                            "burn_rate": burn_rate,
                        }

                tier_specs = [
                    ("PAGE_CRITICAL_FAST_BURN", "critical", "1h", "5m", 14.4, 2.0),
                    ("PAGE_HIGH_BURN", "critical", "6h", "30m", 6.0, 5.0),
                    ("TICKET_MEDIUM_BURN", "warning", "24h", "2h", 3.0, 10.0),
                    ("TICKET_SLOW_BURN", "warning", "72h", "6h", 1.0, 10.0),
                ]
                multi_window_tiers: List[Dict[str, Any]] = []
                firing_tier: Optional[Dict[str, Any]] = None

                for code, severity, long_w, short_w, threshold, budget_pct in tier_specs:
                    long_b = window_burn_map[long_w]["burn_rate"]
                    short_b = window_burn_map[short_w]["burn_rate"]
                    tier_firing = (long_b >= threshold) and (short_b >= threshold)
                    tier_entry = {
                        "tier": code,
                        "severity": severity,
                        "long_window": long_w,
                        "short_window": short_w,
                        "long_burn_rate": long_b,
                        "short_burn_rate": short_b,
                        "threshold": threshold,
                        "budget_consumed_in_long_window_pct": budget_pct,
                        "firing": tier_firing,
                    }
                    multi_window_tiers.append(tier_entry)
                    if tier_firing and firing_tier is None:
                        firing_tier = tier_entry

                # Estimate 72h / primary error budget remaining percentage
                ref_burn = window_burn_map.get("72h", {}).get("burn_rate", burn_rate)
                consumed_pct = min(100.0, max(0.0, round(ref_burn * (72.0 / total_window_hours) * 100.0, 2)))
                remaining_pct = round(100.0 - consumed_pct, 2)

                observations: List[Dict[str, Any]] = []
                if firing_tier is not None:
                    observations.append(
                        {
                            "code": firing_tier["tier"],
                            "burn_rate": firing_tier["long_burn_rate"],
                            "short_burn_rate": firing_tier["short_burn_rate"],
                            "threshold": firing_tier["threshold"],
                        }
                    )
                elif burn_rate >= 14.4:
                    observations.append(
                        {
                            "code": "PAGE_CRITICAL_FAST_BURN",
                            "burn_rate": burn_rate,
                            "threshold": 14.4,
                        }
                    )
                elif burn_rate >= 6.0:
                    observations.append(
                        {
                            "code": "PAGE_HIGH_BURN",
                            "burn_rate": burn_rate,
                            "threshold": 6.0,
                        }
                    )
                elif burn_rate >= 1.0:
                    observations.append(
                        {
                            "code": "TICKET_SLOW_BURN",
                            "burn_rate": burn_rate,
                            "threshold": 1.0,
                        }
                    )
                else:
                    observations.append(
                        {
                            "code": "WITHIN_ERROR_BUDGET",
                            "burn_rate": burn_rate,
                        }
                    )

                return {
                    "backend_id": backend_id,
                    "slo_target": slo_target,
                    "error_budget_fraction": round(error_budget, 6),
                    "error_budget_remaining_pct": remaining_pct,
                    "current_error_rate": round(err_rate, 6),
                    "current_total_rate": round(tot_rate, 6),
                    "current_error_ratio": round(current_error_ratio, 6),
                    "burn_rate_multiplier": burn_rate,
                    "estimated_exhaustion_hours": exhaustion_hours,
                    "windows": window_burn_map,
                    "multi_window_tiers": multi_window_tiers,
                    "observations": observations,
                }
            except Exception as e:
                raise PrometheusQueryError(f"SLO burn evaluation failed: {e}")
