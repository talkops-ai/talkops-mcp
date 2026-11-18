"""TraceQL metrics, N->1 RED service analysis, and span cohort comparison tools."""

import asyncio
import math
from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field
from pydantic.fields import FieldInfo

from tempo_mcp_server.exceptions import (
    TempoOperationError,
    TempoQueryError,
    TempoValidationError,
)
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.response_size import enforce_structured_size_limit
from tempo_mcp_server.utils.time_helpers import duration_to_seconds, resolve_time_params
from tempo_mcp_server.utils.traceql_helpers import normalize_traceql_query, validate_traceql_basic


def _validate_metrics_time_range(
    start: Optional[float],
    end: Optional[float],
    max_duration_str: str,
) -> None:
    """Pre-validate that the resolved time range does not exceed Tempo's max_duration."""
    if start is None or end is None:
        return

    try:
        max_seconds = duration_to_seconds(max_duration_str)
    except ValueError:
        return

    range_seconds = end - start
    if range_seconds > max_seconds:
        hours = range_seconds / 3600
        max_hours = max_seconds / 3600
        raise TempoValidationError(
            f"Requested time range ({hours:.1f}h) exceeds the maximum allowed "
            f"metrics query duration ({max_hours:.1f}h). "
            f"Tempo's query_frontend.metrics.max_duration is set to {max_duration_str}. "
            f"Narrow 'since' to '{max_duration_str}' or less."
        )


def _compute_series_summary(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute factual min/max/avg/latest statistics over a series of points."""
    vals: List[float] = []
    for p in points:
        try:
            v = float(p["value"])
            if not math.isnan(v) and not math.isinf(v):
                vals.append(v)
        except (ValueError, TypeError, KeyError):
            continue

    if not vals:
        return {"point_count": len(points), "min": None, "max": None, "avg": None, "latest": None}

    return {
        "point_count": len(points),
        "min": round(min(vals), 6),
        "max": round(max(vals), 6),
        "avg": round(sum(vals) / len(vals), 6),
        "latest": round(vals[-1], 6),
    }


def _extract_scalar_average(range_response: Dict[str, Any]) -> Optional[float]:
    """Compute mean value across all points of the first series in a range response."""
    data = range_response.get("data", range_response)
    series_list = data.get("result", [])
    if not series_list:
        return None
    vals: List[float] = []
    for s in series_list:
        for v in s.get("values", []):
            try:
                f = float(v[1])
                if not math.isnan(f) and not math.isinf(f):
                    vals.append(f)
            except (ValueError, TypeError, IndexError):
                continue
        if "value" in s and isinstance(s["value"], list) and len(s["value"]) >= 2:
            try:
                f = float(s["value"][1])
                if not math.isnan(f) and not math.isinf(f):
                    vals.append(f)
            except (ValueError, TypeError):
                pass
    if not vals:
        return None
    return round(sum(vals) / len(vals), 6)


class MetricsTools(BaseTool):
    """TraceQL metrics range, instant, N->1 RED analysis, and span cohort comparison tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("metrics", is_write=False):
            return

        tempo_service = self.tempo_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="TraceQL Metrics Range Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_traceql_metrics_range(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            query: str = Field(
                ..., min_length=1,
                description="TraceQL metrics query, e.g. '{ resource.service.name = \"api\" } | rate()'",
            ),
            since: Optional[str] = Field(default="1h", description="Relative time range, e.g. '1h'"),
            start: Optional[float] = Field(default=None, description="Start time as Unix epoch seconds"),
            end: Optional[float] = Field(default=None, description="End time as Unix epoch seconds"),
            step: Optional[str] = Field(default=None, description="Step duration, e.g. '30s', '1m'"),
            sample: Optional[str] = Field(
                default=None,
                description="Optional metrics sampling factor, e.g. '0.1' or 'fixed-span:0.1'",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a TraceQL metrics range query returning time-series points and per-series stats.

            Returns: {"effective_query": str, "result_type": "matrix", "series": [{"labels": {...}, "summary": {...}, "points": [...]}]}.
            When NOT to use: For single-service RED + baseline comparison, call tempo_analyze_service_red.
            """
            query = normalize_traceql_query(query)
            error = validate_traceql_basic(query)
            if error:
                raise TempoQueryError(f"TraceQL validation failed: {error}")

            resolved_start, resolved_end = resolve_time_params(start, end, since)
            max_dur = self.config.query_policy.max_metrics_duration
            _validate_metrics_time_range(resolved_start, resolved_end, max_dur)

            try:
                if ctx:
                    await ctx.info(f"Executing metrics range query on '{backend_id}'...")
                result = await tempo_service.metrics_query_range(
                    backend_id=backend_id,
                    q=query,
                    tenant=tenant,
                    start=resolved_start,
                    end=resolved_end,
                    step=step,
                    sample=sample,
                )

                data = result.get("data", result)
                raw_series = data.get("result", [])

                series = []
                for s in raw_series:
                    points = [
                        {"ts": float(v[0]), "value": str(v[1])}
                        for v in s.get("values", [])
                    ]
                    series.append({
                        "labels": s.get("metric", {}),
                        "summary": _compute_series_summary(points),
                        "points": points,
                    })

                effective_sample = sample or self.config.query_policy.default_metrics_sampling
                payload: Dict[str, Any] = {
                    "effective_query": query,
                    "result_type": data.get("resultType", "matrix"),
                    "series": series,
                    "stats": result.get("stats"),
                }
                if effective_sample:
                    payload["sampling_applied"] = effective_sample

                return enforce_structured_size_limit(
                    payload,
                    truncatable_key="series",
                    max_bytes=self.config.response_size_soft_limit,
                    query_hint=query,
                )
            except Exception as e:
                err_str = str(e).lower()
                if "maximum allowed duration" in err_str:
                    raise TempoValidationError(
                        f"Tempo rejected the metrics query time range: {e}. "
                        f"Narrow 'since' to {max_dur} or less."
                    ) from None
                if any(tok in err_str for tok in ("empty ring", "no generators", "local-blocks", "local_blocks", "metrics_generator", "not enabled", "404")):
                    raise TempoOperationError(
                        "TraceQL metrics are unavailable on this Tempo backend (METRICS_GENERATOR_PROCESSOR_ABSENT: "
                        "'local-blocks' processor inactive in metrics_generator.processors). "
                        "Read 'tempo://server/capabilities', call tempo_get_diagnostics, or fall back to tempo_traceql_search + tempo_summarize_trace."
                    ) from None
                if isinstance(e, (TempoQueryError, TempoValidationError)):
                    raise
                raise TempoOperationError(f"Metrics range query failed: {e}") from None

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="TraceQL Metrics Instant Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_traceql_metrics_instant(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            query: str = Field(..., min_length=1, description="TraceQL metrics query for instant evaluation"),
            since: Optional[str] = Field(default="1h", description="Time window to evaluate over"),
            start: Optional[float] = Field(default=None, description="Start time as Unix epoch seconds"),
            end: Optional[float] = Field(default=None, description="End time as Unix epoch seconds"),
            sample: Optional[str] = Field(default=None, description="Optional metrics sampling factor"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a point-in-time TraceQL metrics instant query (vector format).

            Returns: {"effective_query": str, "result_type": "vector", "result": [...]}.
            When NOT to use: For time-series trends over time, call tempo_traceql_metrics_range.
            """
            query = normalize_traceql_query(query)
            error = validate_traceql_basic(query)
            if error:
                raise TempoQueryError(f"TraceQL validation failed: {error}")

            resolved_start, resolved_end = resolve_time_params(start, end, since)
            max_dur = self.config.query_policy.max_metrics_duration
            _validate_metrics_time_range(resolved_start, resolved_end, max_dur)

            try:
                if ctx:
                    await ctx.info(f"Executing metrics instant query on '{backend_id}'...")
                result = await tempo_service.metrics_query_instant(
                    backend_id=backend_id,
                    q=query,
                    tenant=tenant,
                    start=resolved_start,
                    end=resolved_end,
                    sample=sample,
                )

                data = result.get("data", result)
                effective_sample = sample or self.config.query_policy.default_metrics_sampling
                payload: Dict[str, Any] = {
                    "effective_query": query,
                    "result_type": data.get("resultType", "vector"),
                    "result": data.get("result", []),
                }
                if effective_sample:
                    payload["sampling_applied"] = effective_sample
                return payload
            except Exception as e:
                err_str = str(e).lower()
                if "maximum allowed duration" in err_str:
                    raise TempoValidationError(
                        f"Tempo rejected the metrics query time range: {e}. "
                        f"Narrow 'since' to {max_dur} or less."
                    ) from None
                if any(tok in err_str for tok in ("empty ring", "no generators", "local-blocks", "local_blocks", "metrics_generator", "not enabled", "404")):
                    raise TempoOperationError(
                        "TraceQL metrics are unavailable on this Tempo backend (METRICS_GENERATOR_PROCESSOR_ABSENT: "
                        "'local-blocks' processor inactive in metrics_generator.processors). "
                        "Read 'tempo://server/capabilities', call tempo_get_diagnostics, or fall back to tempo_traceql_search + tempo_summarize_trace."
                    ) from None
                if isinstance(e, (TempoQueryError, TempoValidationError)):
                    raise
                raise TempoOperationError(f"Metrics instant query failed: {e}") from None

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Analyze Service RED Metrics",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_analyze_service_red(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            service: str = Field(..., min_length=1, description="Target resource.service.name"),
            since: str = Field(default="15m", description="Current evaluation window, e.g. '15m', '1h'"),
            baseline_offset: Optional[str] = Field(
                default=None,
                description="Optional prior window duration before current window for delta calculation, e.g. '1h'",
            ),
            group_by: Optional[str] = Field(
                default=None,
                description="Optional attribute to group by, e.g. 'span:name'",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Compute factual Rate, Error rate, and P50/P95/P99 latency metrics, optional baseline deltas, and exemplar IDs.

            Returns: {"service": str, "current": {"rate_rps": float, "error_rate_rps": float, "error_ratio": float, "p50_ms": float, "p95_ms": float, "p99_ms": float}, "baseline": {...}|null, "deltas": {...}|null, "exemplar_trace_ids": [...]}.
            When NOT to use: For custom non-RED TraceQL metrics pipelines, call tempo_traceql_metrics_range.
            """
            if isinstance(since, FieldInfo):
                since = since.default
            if isinstance(baseline_offset, FieldInfo):
                baseline_offset = baseline_offset.default
            if isinstance(group_by, FieldInfo):
                group_by = group_by.default
            if isinstance(tenant, FieldInfo):
                tenant = tenant.default
            cur_start, cur_end = resolve_time_params(since=since)
            max_dur = self.config.query_policy.max_metrics_duration
            _validate_metrics_time_range(cur_start, cur_end, max_dur)

            by_clause = f" by ({group_by})" if group_by else ""
            q_rate = f'{{ resource.service.name = "{service}" }} | rate(){by_clause}'
            q_err = f'{{ resource.service.name = "{service}" && status = error }} | rate(){by_clause}'
            q_p50 = f'{{ resource.service.name = "{service}" }} | quantile_over_time(duration, 0.5){by_clause}'
            q_p95 = f'{{ resource.service.name = "{service}" }} | quantile_over_time(duration, 0.95){by_clause}'
            q_p99 = f'{{ resource.service.name = "{service}" }} | quantile_over_time(duration, 0.99){by_clause}'

            try:
                if ctx:
                    await ctx.info(f"Running N->1 RED metrics aggregation for service '{service}'...")

                rate_res, err_res, p50_res, p95_res, p99_res = await asyncio.gather(
                    tempo_service.metrics_query_range(
                        backend_id=backend_id, q=q_rate, tenant=tenant, start=cur_start, end=cur_end
                    ),
                    tempo_service.metrics_query_range(
                        backend_id=backend_id, q=q_err, tenant=tenant, start=cur_start, end=cur_end, exemplars=True
                    ),
                    tempo_service.metrics_query_range(
                        backend_id=backend_id, q=q_p50, tenant=tenant, start=cur_start, end=cur_end
                    ),
                    tempo_service.metrics_query_range(
                        backend_id=backend_id, q=q_p95, tenant=tenant, start=cur_start, end=cur_end
                    ),
                    tempo_service.metrics_query_range(
                        backend_id=backend_id, q=q_p99, tenant=tenant, start=cur_start, end=cur_end, exemplars=True
                    ),
                )

                cur_rate = _extract_scalar_average(rate_res) or 0.0
                cur_err = _extract_scalar_average(err_res) or 0.0
                cur_ratio = round(cur_err / cur_rate, 6) if cur_rate > 0 else 0.0
                cur_p50 = _extract_scalar_average(p50_res)
                cur_p95 = _extract_scalar_average(p95_res)
                cur_p99 = _extract_scalar_average(p99_res)

                exemplar_ids: List[str] = []
                for ex_source in (err_res, p99_res):
                    data_block = ex_source.get("data", ex_source)
                    for ex in data_block.get("exemplars", []):
                        tid = ex.get("traceID")
                        if tid and tid not in exemplar_ids:
                            exemplar_ids.append(tid)

                current_metrics = {
                    "window": since,
                    "rate_rps": cur_rate,
                    "error_rate_rps": cur_err,
                    "error_ratio": cur_ratio,
                    "p50_duration": cur_p50,
                    "p95_duration": cur_p95,
                    "p99_duration": cur_p99,
                    "p50_ms": round(cur_p50 * 1000.0, 2) if (cur_p50 is not None and cur_p50 < 600) else cur_p50,
                    "p95_ms": round(cur_p95 * 1000.0, 2) if (cur_p95 is not None and cur_p95 < 600) else cur_p95,
                    "p99_ms": round(cur_p99 * 1000.0, 2) if (cur_p99 is not None and cur_p99 < 600) else cur_p99,
                }

                baseline_metrics: Optional[Dict[str, Any]] = None
                deltas: Optional[Dict[str, Any]] = None

                if baseline_offset and cur_start is not None:
                    offset_sec = duration_to_seconds(baseline_offset)
                    win_sec = (cur_end - cur_start) if cur_end else duration_to_seconds(since)
                    base_end = cur_start - max(0.0, offset_sec - win_sec)
                    base_start = base_end - win_sec

                    b_rate_res, b_err_res, b_p99_res = await asyncio.gather(
                        tempo_service.metrics_query_range(
                            backend_id=backend_id, q=q_rate, tenant=tenant, start=base_start, end=base_end
                        ),
                        tempo_service.metrics_query_range(
                            backend_id=backend_id, q=q_err, tenant=tenant, start=base_start, end=base_end
                        ),
                        tempo_service.metrics_query_range(
                            backend_id=backend_id, q=q_p99, tenant=tenant, start=base_start, end=base_end
                        ),
                    )
                    b_rate = _extract_scalar_average(b_rate_res) or 0.0
                    b_err = _extract_scalar_average(b_err_res) or 0.0
                    b_ratio = round(b_err / b_rate, 6) if b_rate > 0 else 0.0
                    b_p99 = _extract_scalar_average(b_p99_res)

                    baseline_metrics = {
                        "baseline_offset": baseline_offset,
                        "rate_rps": b_rate,
                        "error_rate_rps": b_err,
                        "error_ratio": b_ratio,
                        "p99_duration": b_p99,
                    }

                    rate_delta_pct = (
                        round(((cur_rate - b_rate) / b_rate) * 100.0, 2)
                        if b_rate > 0
                        else None
                    )
                    p99_delta_pct = (
                        round(((cur_p99 - b_p99) / b_p99) * 100.0, 2)
                        if (cur_p99 is not None and b_p99 and b_p99 > 0)
                        else None
                    )
                    deltas = {
                        "rate_delta_pct": rate_delta_pct,
                        "error_ratio_delta": round(cur_ratio - b_ratio, 6),
                        "p99_duration_delta_pct": p99_delta_pct,
                    }

                return {
                    "backend_id": backend_id,
                    "service": service,
                    "current": current_metrics,
                    "baseline": baseline_metrics,
                    "deltas": deltas,
                    "exemplar_trace_ids": exemplar_ids[:10],
                }
            except Exception as e:
                err_str = str(e).lower()
                if any(tok in err_str for tok in ("empty ring", "no generators", "local-blocks", "local_blocks", "metrics_generator", "not enabled")):
                    raise TempoOperationError(
                        f"TraceQL metrics unavailable for '{service}' on backend '{backend_id}' "
                        "(METRICS_GENERATOR_PROCESSOR_ABSENT: 'local-blocks' disabled). "
                        "Fall back to tempo_traceql_search + tempo_summarize_trace."
                    ) from None
                if isinstance(e, (TempoQueryError, TempoValidationError)):
                    raise
                self.handle_error(e, "tempo_analyze_service_red", backend_id=backend_id, resource_name=service)
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Compare Span Cohorts (TraceQL compare())",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_compare_span_cohorts(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            base_query: str = Field(
                ..., min_length=1,
                description="Base TraceQL span selector, e.g. '{ resource.service.name = \"api\" }'",
            ),
            selection: str = Field(
                ..., min_length=1,
                description="Selection cohort filter, e.g. '{ span:status = error }' or '{ span:duration > 1s }'",
            ),
            since: str = Field(default="1h", description="Evaluation time window, e.g. '1h'"),
            top_n: int = Field(default=10, ge=1, le=50, description="Top N values per attribute"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a TraceQL compare() instant query to rank attribute values differentiating selection vs baseline spans.

            Returns: {"effective_query": str, "divergent_attributes": [{"attribute": str, "value": str, "selection_count": float, "baseline_count": float, "skew_delta": float}]}.
            When NOT to use: For comparing two individual trace IDs, call tempo_compare_traces.
            """
            if isinstance(since, FieldInfo):
                since = since.default
            if isinstance(top_n, FieldInfo):
                top_n = top_n.default
            if isinstance(tenant, FieldInfo):
                tenant = tenant.default
            norm_base = normalize_traceql_query(base_query)
            norm_sel = normalize_traceql_query(selection)
            err_b = validate_traceql_basic(norm_base)
            err_s = validate_traceql_basic(norm_sel)
            if err_b or err_s:
                raise TempoQueryError(f"TraceQL validation failed: {err_b or err_s}")

            effective_query = f"{norm_base} | compare({norm_sel}, {top_n})"
            resolved_start, resolved_end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info(f"Executing cohort comparison: {effective_query}...")
                result = await tempo_service.metrics_query_instant(
                    backend_id=backend_id,
                    q=effective_query,
                    tenant=tenant,
                    start=resolved_start,
                    end=resolved_end,
                )

                data = result.get("data", result)
                raw_series = data.get("result", [])

                # Group by (attribute_name, attribute_value) across __meta_type = selection | baseline
                # Compute selection_share and baseline_share PER attribute_name so multi-attribute compare()
                # outputs preserve true 0..100% cohort share (e.g. >=80% canary skew, >=60% pod skew).
                buckets: Dict[tuple[str, str], Dict[str, float]] = {}
                attr_totals: Dict[str, Dict[str, float]] = {}
                explicit_totals: Dict[str, Dict[str, float]] = {}

                for item in raw_series:
                    metric = dict(item.get("metric", {}))
                    meta_type = metric.pop("__meta_type", "selection")
                    val_pair = item.get("value") or (item.get("values", [[0, "0"]])[0])
                    try:
                        count = float(val_pair[1])
                    except (ValueError, TypeError, IndexError):
                        count = 0.0

                    if meta_type in ("selection_total", "baseline_total"):
                        tot_kind = "selection" if meta_type == "selection_total" else "baseline"
                        for attr_key in metric.keys():
                            explicit_totals.setdefault(str(attr_key), {"selection": 0.0, "baseline": 0.0})[tot_kind] += count
                        continue

                    for attr_key, attr_val in metric.items():
                        ak = str(attr_key)
                        av = str(attr_val)
                        key = (ak, av)
                        entry = buckets.setdefault(key, {"selection": 0.0, "baseline": 0.0})
                        atot = attr_totals.setdefault(ak, {"selection": 0.0, "baseline": 0.0})
                        if meta_type == "baseline":
                            entry["baseline"] += count
                            atot["baseline"] += count
                        else:
                            entry["selection"] += count
                            atot["selection"] += count

                divergent: List[Dict[str, Any]] = []
                for (attr_key, attr_val), counts in buckets.items():
                    sel_c = counts["selection"]
                    base_c = counts["baseline"]
                    if sel_c == 0.0 and base_c == 0.0:
                        continue
                    sel_denom = (
                        explicit_totals.get(attr_key, {}).get("selection")
                        or attr_totals.get(attr_key, {}).get("selection")
                        or 0.0
                    )
                    base_denom = (
                        explicit_totals.get(attr_key, {}).get("baseline")
                        or attr_totals.get(attr_key, {}).get("baseline")
                        or 0.0
                    )
                    sel_share = (sel_c / sel_denom) if sel_denom > 0 else 0.0
                    base_share = (base_c / base_denom) if base_denom > 0 else 0.0
                    skew = round(sel_share - base_share, 6)
                    divergent.append({
                        "attribute": attr_key,
                        "value": attr_val,
                        "selection_count": sel_c,
                        "baseline_count": base_c,
                        "selection_share": round(sel_share, 4),
                        "baseline_share": round(base_share, 4),
                        "skew_delta": skew,
                    })

                divergent.sort(key=lambda d: (abs(d["skew_delta"]), d["selection_count"]), reverse=True)

                return {
                    "effective_query": effective_query,
                    "divergent_attributes": divergent[: top_n * 3],
                    "raw_series_count": len(raw_series),
                }
            except Exception as e:
                err_str = str(e).lower()
                if any(tok in err_str for tok in ("empty ring", "no generators", "local-blocks", "local_blocks", "metrics_generator", "not enabled")):
                    raise TempoOperationError(
                        f"TraceQL metrics compare() unavailable on backend '{backend_id}' "
                        "(METRICS_GENERATOR_PROCESSOR_ABSENT: 'local-blocks' disabled). "
                        "Fall back to tempo_traceql_search + tempo_summarize_trace."
                    ) from None
                if isinstance(e, (TempoQueryError, TempoValidationError)):
                    raise
                self.handle_error(e, "tempo_compare_span_cohorts", backend_id=backend_id)
                raise
