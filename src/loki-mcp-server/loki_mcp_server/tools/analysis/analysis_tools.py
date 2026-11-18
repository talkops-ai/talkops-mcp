"""Compound N-to-1 analytical, correlation, and FinOps tools.

Tools (`analysis` toolset, all read-only, <= 8 parameters):
- loki_summarize_service_logs: Compute log rate, error rate/ratio, severity distribution,
  top error signatures, and extracted trace_ids for a stream selector in one turn.
- loki_compare_periods: Compare log volume, error rate, and emerging error patterns
  between a target window and a baseline offset or canary selector.
- loki_correlate_trace_logs: Search across services for a trace_id, span_id, or request_id
  using structured metadata or line filters (never in {}) and build a chronological timeline.
- loki_analyze_volume: Attribute ingested bytes and stream counts by label using
  /loki/api/v1/index/volume with automatic bytes_over_time fallback.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.exceptions import LokiValidationError
from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.logql_helpers import (
    detect_high_cardinality_in_selector,
    format_log_entries,
    validate_stream_selector,
)
from loki_mcp_server.utils.time_utils import (
    _parse_to_datetime,
    parse_relative_time,
    validate_time_window,
)

_TRACE_ID_RE = re.compile(
    r'(?:trace_id|traceId|traceID|traceparent)["\s:=]+([0-9a-fA-F-]{16,64})'
)
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUM_RE = re.compile(r"\b\d+\b")


def _normalize_signature(line: str) -> str:
    """Normalize dynamic numbers, UUIDs, and hex strings in a log line for clustering."""
    s = line.strip()
    if len(s) > 220:
        s = s[:220]
    s = _HEX_RE.sub("<hex>", s)
    s = _NUM_RE.sub("<num>", s)
    return s


def _extract_trace_ids_from_streams(streams: List[Dict[str, Any]]) -> List[str]:
    """Extract unique trace IDs from stream labels (structured metadata) and log lines."""
    found: List[str] = []
    seen: set[str] = set()
    for stream in streams:
        labels = stream.get("stream", {}) or stream.get("labels", {})
        for key in ("trace_id", "traceID", "traceId"):
            val = labels.get(key)
            if val and str(val) not in seen:
                seen.add(str(val))
                found.append(str(val))
        entries = stream.get("values") or stream.get("entries") or []
        for entry in entries:
            line = entry[1] if isinstance(entry, (list, tuple)) and len(entry) > 1 else (
                entry.get("line", "") if isinstance(entry, dict) else ""
            )
            for m in _TRACE_ID_RE.findall(str(line)):
                if m not in seen:
                    seen.add(m)
                    found.append(m)
    return found[:20]


def _extract_scalar_from_result(data: Dict[str, Any]) -> float:
    """Extract a summed scalar float from a Loki vector or matrix response."""
    res = data.get("result", [])
    total = 0.0
    for item in res:
        if "value" in item and isinstance(item["value"], (list, tuple)) and len(item["value"]) >= 2:
            try:
                total += float(item["value"][1])
            except (ValueError, TypeError):
                pass
        elif "values" in item and isinstance(item["values"], list) and item["values"]:
            vals = []
            for pt in item["values"]:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        vals.append(float(pt[1]))
                    except (ValueError, TypeError):
                        pass
            if vals:
                total += sum(vals) / len(vals)
    return round(total, 6)


class AnalysisTools(BaseTool):
    """Compound N-to-1 analytical and FinOps tools (`analysis` toolset)."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        loki = self.loki_service
        config = self.config
        if not config.should_register("analysis", is_write=False):
            return

        # ──────────────────────────────────────────
        # Tool 10: loki_summarize_service_logs
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Summarize Service Logs (N-to-1 Triage)",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_summarize_service_logs(
            selector: str = Field(
                ...,
                min_length=1,
                description="LogQL stream selector wrapped in braces (e.g., '{app=\"checkout\"}')",
            ),
            start: str = Field(
                default="now-1h",
                description="Start timestamp (RFC3339 or relative like 'now-1h')",
            ),
            end: str = Field(
                default="now",
                description="End timestamp (RFC3339 or relative like 'now')",
            ),
            error_pattern: str = Field(
                default="(?i)error|exception|fatal|panic",
                description="Regex line filter used to identify error log lines",
            ),
            sample_limit: int = Field(
                default=10,
                ge=1,
                le=50,
                description="Max sample error log lines to include (1-50)",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Compute a high-signal service log health & error summary in one call.

            Aggregates index stats, total log rate, error rate/ratio, top recurring
            error signatures, sample error lines, and extracted `trace_id` values
            for cross-pillar pivoting to Tempo. Read-only.
            """
            selector = validate_stream_selector(selector)
            warnings: List[str] = []
            hc_labels = detect_high_cardinality_in_selector(selector)
            if hc_labels:
                warnings.append(
                    f"High-cardinality labels in selector: {hc_labels}. "
                    "Move to structured metadata or line filters."
                )

            s = parse_relative_time(start)
            e = parse_relative_time(end)
            validate_time_window(s, e, max_hours=config.guardrails.max_time_window_hours)

            if ctx:
                await ctx.info(f"Summarizing service logs for {selector} ({start} -> {end})...")

            # 1. Index stats
            stats: Dict[str, Any] = {}
            try:
                stats = await loki.get_index_stats(
                    query=selector, start=s, end=e, org_id=org_id
                )
            except Exception:
                stats = {"streams": 0, "chunks": 0, "entries": 0, "bytes": 0}

            # 2. Sample error logs
            error_query = f'{selector} |~ "{error_pattern}"'
            error_data = await loki.query_range(
                query=error_query,
                start=s,
                end=e,
                limit=min(sample_limit * 3, 100),
                org_id=org_id,
            )
            raw_streams = error_data.get("result", [])
            formatted_errors = format_log_entries(raw_streams, max_lines=sample_limit)

            # Cluster error signatures and count severity levels
            sig_counter: Counter[str] = Counter()
            severity_counter: Counter[str] = Counter()
            sampled_error_count = 0
            for stream in raw_streams:
                lbls = stream.get("stream", {})
                lvl = (
                    lbls.get("level")
                    or lbls.get("detected_level")
                    or lbls.get("severity")
                    or "error"
                )
                vals = stream.get("values", [])
                severity_counter[str(lvl).lower()] += len(vals)
                for entry in vals:
                    sampled_error_count += 1
                    if isinstance(entry, (list, tuple)) and len(entry) > 1:
                        sig_counter[_normalize_signature(str(entry[1]))] += 1

            trace_ids = _extract_trace_ids_from_streams(raw_streams)
            total_entries = int(stats.get("entries", 0)) or sampled_error_count
            error_ratio = (
                round(sampled_error_count / total_entries, 4)
                if total_entries > 0
                else 0.0
            )

            status = "NOMINAL"
            if sampled_error_count >= 20 or error_ratio >= 0.05:
                status = "CRITICAL"
            elif sampled_error_count > 0:
                status = "WARNING"

            return {
                "selector": selector,
                "window": {"start": start, "end": end},
                "status": status,
                "index_stats": {
                    "streams": stats.get("streams", 0),
                    "chunks": stats.get("chunks", 0),
                    "entries": stats.get("entries", 0),
                    "bytes": stats.get("bytes", 0),
                },
                "error_summary": {
                    "sampled_error_lines": sampled_error_count,
                    "estimated_error_ratio": error_ratio,
                    "severity_breakdown": dict(severity_counter),
                    "top_error_signatures": [
                        {"signature": sig, "count": cnt}
                        for sig, cnt in sig_counter.most_common(5)
                    ],
                },
                "extracted_trace_ids": trace_ids,
                "sample_error_streams": formatted_errors,
                "warnings": warnings,
            }

        # ──────────────────────────────────────────
        # Tool 11: loki_compare_periods
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Compare Log Periods or Deployments (N-to-1 Diff)",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_compare_periods(
            selector: str = Field(
                ...,
                min_length=1,
                description="Current LogQL stream selector (e.g., '{app=\"checkout\"}')",
            ),
            start: str = Field(
                default="now-15m",
                description="Current window start (e.g., 'now-15m')",
            ),
            end: str = Field(
                default="now",
                description="Current window end (e.g., 'now')",
            ),
            baseline_offset: Optional[str] = Field(
                default=None,
                description="Lookback offset for baseline comparison (e.g., '1h', '24h'). Defaults to '0s' when baseline_selector differs from selector, else '1h'.",
            ),
            baseline_selector: Optional[str] = Field(
                default=None,
                description="Optional distinct baseline selector (e.g., '{app=\"checkout\", version=\"v1\"}')",
            ),
            error_filter: str = Field(
                default="error",
                description="Substring or regex filter for error lines (default: 'error')",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Compare log volume, error counts, and error signatures across two windows or versions.

            Detects newly emerging error signatures after a deployment or incident onset
            without requiring multiple sequential tool calls. Read-only.
            """
            from datetime import timedelta

            selector = validate_stream_selector(selector)
            base_sel = (
                validate_stream_selector(baseline_selector)
                if baseline_selector
                else selector
            )

            s_curr = parse_relative_time(start)
            e_curr = parse_relative_time(end)
            validate_time_window(
                s_curr, e_curr, max_hours=config.guardrails.max_time_window_hours
            )

            effective_offset = (
                baseline_offset.strip()
                if baseline_offset and baseline_offset.strip()
                else ("0s" if (baseline_selector and base_sel != selector) else "1h")
            )

            # Compute baseline time window by shifting start/end by effective_offset
            offset_Match = re.match(r"^(\d+)([smhdw])$", effective_offset)
            unit_seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
            if offset_Match:
                shift_sec = int(offset_Match.group(1)) * unit_seconds[offset_Match.group(2)]
            elif effective_offset in ("0", "none"):
                shift_sec = 0
            else:
                shift_sec = 3600

            if shift_sec > 0:
                try:
                    s_base = (
                        _parse_to_datetime(s_curr) - timedelta(seconds=shift_sec)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    e_base = (
                        _parse_to_datetime(e_curr) - timedelta(seconds=shift_sec)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    s_base = s_curr
                    e_base = e_curr
            else:
                s_base = s_curr
                e_base = e_curr

            if ctx:
                await ctx.info(
                    f"Comparing {selector} against baseline ({effective_offset})..."
                )

            if error_filter.strip().lower() == "error":
                filter_stage = '|~ "(?i)error|exception|fatal|panic"'
            else:
                filter_stage = f'|= "{error_filter}"'

            curr_err_q = f"{selector} {filter_stage}"
            base_err_q = f"{base_sel} {filter_stage}"

            curr_data = await loki.query_range(
                query=curr_err_q, start=s_curr, end=e_curr, limit=100, org_id=org_id
            )
            base_data = await loki.query_range(
                query=base_err_q, start=s_base, end=e_base, limit=100, org_id=org_id
            )

            def _extract_sigs(data: Dict[str, Any]) -> tuple[int, Counter[str]]:
                cnt = 0
                sigs: Counter[str] = Counter()
                for st in data.get("result", []):
                    for entry in st.get("values", []):
                        cnt += 1
                        if isinstance(entry, (list, tuple)) and len(entry) > 1:
                            sigs[_normalize_signature(str(entry[1]))] += 1
                return cnt, sigs

            curr_count, curr_sigs = _extract_sigs(curr_data)
            base_count, base_sigs = _extract_sigs(base_data)

            delta_count = curr_count - base_count
            delta_pct = (
                round(((curr_count - base_count) / base_count) * 100.0, 2)
                if base_count > 0
                else (100.0 if curr_count > 0 else 0.0)
            )

            new_signatures = [
                {"signature": sig, "current_count": count}
                for sig, count in curr_sigs.most_common(5)
                if sig not in base_sigs
            ]

            return {
                "current_selector": selector,
                "baseline_selector": base_sel,
                "baseline_offset": effective_offset,
                "current_error_count": curr_count,
                "baseline_error_count": base_count,
                "error_count_delta": delta_count,
                "error_count_delta_pct": delta_pct,
                "regression_detected": curr_count > base_count and (delta_pct >= 25.0 or len(new_signatures) > 0),
                "new_error_signatures": new_signatures,
                "top_current_signatures": [
                    {"signature": sig, "count": cnt}
                    for sig, cnt in curr_sigs.most_common(5)
                ],
            }

        # ──────────────────────────────────────────
        # Tool 12: loki_correlate_trace_logs
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Correlate Logs by Trace or Request ID",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_correlate_trace_logs(
            correlation_id: str = Field(
                ...,
                min_length=4,
                description="Trace ID, Span ID, or Request ID to search across services (e.g., '4bf92f3577b34da6a3ce929d0e0e4736')",
            ),
            scope_selector: str = Field(
                default='{app=~".+"}',
                description="Low-cardinality stream selector scope (never put trace_id in {})",
            ),
            correlation_key: str = Field(
                default="trace_id",
                description="Structured metadata / JSON key name (e.g., 'trace_id', 'request_id', 'span_id')",
            ),
            start: str = Field(
                default="now-1h",
                description="Start timestamp (RFC3339 or relative like 'now-1h')",
            ),
            end: str = Field(
                default="now",
                description="End timestamp (RFC3339 or relative like 'now')",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Find and chronologically order all logs matching a trace_id or request_id.

            Enforces Loki cardinality guardrails by querying via structured metadata
            or line filter (`|= "<correlation_id>"`) outside `{}` stream selectors.
            Returns participating services and timeline entries for Tempo handoff.
            """
            scope_selector = validate_stream_selector(scope_selector)
            hc = detect_high_cardinality_in_selector(scope_selector)
            if hc:
                raise LokiValidationError(
                    f"High-cardinality key(s) {hc} detected inside scope_selector '{scope_selector}'. "
                    "Pass only low-cardinality labels (app, namespace, cluster) in scope_selector."
                )

            s = parse_relative_time(start)
            e = parse_relative_time(end)
            validate_time_window(s, e, max_hours=config.guardrails.max_time_window_hours)

            clean_id = correlation_id.strip().strip('"').strip("'")
            clean_key = correlation_key.strip() or "trace_id"
            line_query = f'{scope_selector} |= "{clean_id}"'
            meta_query = (
                f'{scope_selector} | {clean_key}="{clean_id}"'
                if re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", clean_key)
                else None
            )

            if ctx:
                await ctx.info(f"Correlating logs for {clean_key}={clean_id}...")

            raw_streams: List[Dict[str, Any]] = []
            if meta_query:
                try:
                    meta_data = await loki.query_range(
                        query=meta_query,
                        start=s,
                        end=e,
                        limit=100,
                        direction="forward",
                        org_id=org_id,
                    )
                    raw_streams.extend(meta_data.get("result", []))
                except Exception:
                    pass

            line_data = await loki.query_range(
                query=line_query,
                start=s,
                end=e,
                limit=100,
                direction="forward",
                org_id=org_id,
            )
            raw_streams.extend(line_data.get("result", []))

            timeline: List[Dict[str, Any]] = []
            services: List[str] = []
            seen_services: set[str] = set()
            seen_entries: set[tuple[str, str, str]] = set()

            for stream in raw_streams:
                labels = stream.get("stream", {})
                svc = (
                    labels.get("service_name")
                    or labels.get("app")
                    or labels.get("job")
                    or "unknown"
                )
                if svc not in seen_services:
                    seen_services.add(svc)
                    services.append(svc)

                for entry in stream.get("values", []):
                    if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        ts_str = str(entry[0])
                        line_str = str(entry[1])[:1000]
                        dedup_key = (ts_str, svc, line_str)
                        if dedup_key in seen_entries:
                            continue
                        seen_entries.add(dedup_key)
                        timeline.append(
                            {
                                "timestamp": ts_str,
                                "service": svc,
                                "labels": labels,
                                "line": line_str,
                            }
                        )

            timeline.sort(key=lambda item: item["timestamp"])
            executed_q = f"{meta_query} (with fallback {line_query})" if meta_query else line_query

            return {
                "correlation_key": clean_key,
                "correlation_id": clean_id,
                "executed_query": executed_q,
                "participating_services": services,
                "total_matched_lines": len(timeline),
                "timeline": timeline[:50],
                "tempo_pivot_hint": {
                    "trace_id": clean_id,
                    "suggested_tool": "tempo_get_trace",
                },
            }

        # ──────────────────────────────────────────
        # Tool 13: loki_analyze_volume
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Analyze Log Volume & FinOps Attribution",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_analyze_volume(
            query: str = Field(
                ...,
                min_length=1,
                description="LogQL stream selector to analyze volume for (e.g., '{namespace=\"prod\"}')",
            ),
            target_label: str = Field(
                default="app",
                description="Label dimension to group byte volume by (e.g., 'app', 'namespace', 'level')",
            ),
            start: str = Field(
                default="now-6h",
                description="Start timestamp (RFC3339 or relative like 'now-6h')",
            ),
            end: str = Field(
                default="now",
                description="End timestamp (RFC3339 or relative like 'now')",
            ),
            limit: int = Field(
                default=20,
                ge=1,
                le=100,
                description="Max top volume series to return (default: 20)",
            ),
            aggregate_by: Literal["labels", "series"] = Field(
                default="labels",
                description="Aggregation mode for /loki/api/v1/index/volume ('labels' or 'series')",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Attribute ingested log bytes and stream counts by label for FinOps optimization.

            Queries `/loki/api/v1/index/volume` and falls back to
            `topk(limit, sum by (target_label) (bytes_over_time(...)))` if the
            Index Volume endpoint is disabled on the Loki backend. Read-only.
            """
            query = validate_stream_selector(query)
            s = parse_relative_time(start)
            e = parse_relative_time(end)
            validate_time_window(s, e, max_hours=config.guardrails.max_time_window_hours)

            if ctx:
                await ctx.info(
                    f"Analyzing log volume for {query} grouped by '{target_label}'..."
                )

            source = "index_volume_api"
            breakdown: List[Dict[str, Any]] = []

            try:
                eff_agg = "series" if target_label else aggregate_by
                vol_data = await loki.get_index_volume(
                    query=query,
                    start=s,
                    end=e,
                    limit=limit,
                    target_labels=target_label,
                    aggregate_by=eff_agg,
                    org_id=org_id,
                )
                raw_results = vol_data.get("result", []) if isinstance(vol_data, dict) else []
                for item in raw_results:
                    metric = item.get("metric", {})
                    val_pair = item.get("value", [0, "0"])
                    vol_bytes = (
                        int(float(val_pair[1]))
                        if isinstance(val_pair, (list, tuple)) and len(val_pair) >= 2
                        else 0
                    )
                    breakdown.append(
                        {
                            "labels": metric,
                            "bytes": vol_bytes,
                            "human_bytes": f"{vol_bytes / 1e6:.2f} MB"
                            if vol_bytes >= 1e6
                            else f"{vol_bytes} B",
                        }
                    )
                if not breakdown or (
                    target_label
                    and all(not str(b.get("labels", {}).get(target_label, "")).strip() for b in breakdown)
                ):
                    raise RuntimeError("index/volume returned unattributed in-memory streams; falling back to bytes_over_time")
            except Exception:
                source = "logql_bytes_over_time_fallback"
                try:
                    win_mins = max(
                        5,
                        int((_parse_to_datetime(e) - _parse_to_datetime(s)).total_seconds() // 60),
                    )
                    win_expr = f"{win_mins}m"
                except Exception:
                    win_expr = "6h"
                fallback_q = f"topk({limit}, sum by ({target_label}) (bytes_over_time({query}[{win_expr}])))"
                instant_data = await loki.query_instant(
                    query=fallback_q, time=e, org_id=org_id
                )
                breakdown = []
                for item in instant_data.get("result", []):
                    metric = item.get("metric", {})
                    val = _extract_scalar_from_result({"result": [item]})
                    vol_bytes = int(val)
                    breakdown.append(
                        {
                            "labels": metric,
                            "bytes": vol_bytes,
                            "human_bytes": f"{vol_bytes / 1e6:.2f} MB"
                            if vol_bytes >= 1e6
                            else f"{vol_bytes} B",
                        }
                    )

            breakdown.sort(key=lambda x: x["bytes"], reverse=True)
            total_bytes = sum(item["bytes"] for item in breakdown)

            return {
                "query": query,
                "target_label": target_label,
                "source": source,
                "total_attributed_bytes": total_bytes,
                "top_producers": breakdown[:limit],
                "count": len(breakdown[:limit]),
            }
