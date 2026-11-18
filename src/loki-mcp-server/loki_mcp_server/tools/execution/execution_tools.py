"""Execution tools — LogQL instant, range, and A2UI query execution.

Tools (`query` toolset, read-only):
- loki_query_instant
- loki_query_range
- loki_query_a2ui
"""

import json as _json
import re as _re
from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.exceptions import LokiQueryTooExpensiveError
from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.logql_helpers import (
    _MAX_LINE_CHARS,
    _MAX_PAYLOAD_BYTES,
    detect_high_cardinality_in_selector,
    format_log_entries,
    validate_stream_selector,
)
from loki_mcp_server.utils.response_size import enforce_structured_size_limit
from loki_mcp_server.utils.time_utils import (
    _parse_to_datetime,
    parse_relative_time,
    validate_time_window,
)

_METRIC_QUERY_RE = _re.compile(
    r"\b(?:rate|rate_counter|count_over_time|bytes_over_time|bytes_rate|"
    r"absent_over_time|sum_over_time|avg_over_time|min_over_time|max_over_time|"
    r"stddev_over_time|stdvar_over_time|quantile_over_time|first_over_time|"
    r"last_over_time)\s*\("
)


class ExecutionTools(BaseTool):
    """LogQL query execution tools (`query` toolset)."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all execution tools with the MCP instance."""
        loki = self.loki_service
        config = self.config
        if not config.should_register("query", is_write=False):
            return

        # ──────────────────────────────────────────
        # Tool 7: loki_query_instant
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Execute Loki Instant Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_query_instant(
            query: str = Field(
                ...,
                min_length=1,
                description="LogQL query containing a stream selector wrapped in braces (e.g., 'rate({app=\"checkout\"} |= \"error\" [5m])')",
            ),
            time: Optional[str] = Field(
                default=None,
                description="Evaluation timestamp (RFC3339 or relative). Defaults to 'now'.",
            ),
            limit: Optional[int] = Field(
                default=None,
                description="Maximum log entries (default 100)",
            ),
            direction: Optional[str] = Field(
                default=None,
                description="Sort order: 'forward' or 'backward' (default backward)",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID) for multi-tenant Loki",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Evaluate a LogQL metric or stream query at a single point in time. Read-only."""
            query = validate_stream_selector(query)

            warnings: List[str] = []
            hc_labels = detect_high_cardinality_in_selector(query)
            if hc_labels:
                warnings.append(
                    f"High-cardinality labels in stream selector: {hc_labels}."
                )

            t = parse_relative_time(time) if time else None

            params: Dict[str, Any] = {}
            if limit is not None:
                params["limit"] = min(limit, config.guardrails.max_log_limit)
            if direction:
                params["direction"] = direction

            if ctx:
                await ctx.info("Executing instant query...")

            data = await loki.query_instant(query=query, time=t, org_id=org_id, **params)

            result_type = data.get("resultType", "unknown")
            raw_result = data.get("result", [])

            if ctx:
                await ctx.info(f"Got {result_type} result with {len(raw_result)} entries")

            if result_type == "streams":
                formatted = format_log_entries(
                    raw_result,
                    max_lines=config.guardrails.max_log_limit,
                )
                return enforce_structured_size_limit(
                    {
                        "result_type": result_type,
                        "result": formatted,
                        "warnings": warnings,
                    },
                    truncatable_key="result",
                    max_bytes=config.response_size_soft_limit,
                    query_hint=query,
                )

            return enforce_structured_size_limit(
                {
                    "result_type": result_type,
                    "result": raw_result,
                    "warnings": warnings,
                },
                truncatable_key="result",
                max_bytes=config.response_size_soft_limit,
                query_hint=query,
            )

        # ──────────────────────────────────────────
        # Tool 8: loki_query_range
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Execute Loki Range Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_query_range(
            query: str = Field(
                ...,
                min_length=1,
                description="LogQL query containing a stream selector wrapped in braces (e.g., '{app=\"checkout\"} |= \"error\" | json')",
            ),
            start: str = Field(
                default="now-1h",
                description="Start timestamp (RFC3339 or relative like 'now-1h')",
            ),
            end: str = Field(
                default="now",
                description="End timestamp (RFC3339 or relative like 'now')",
            ),
            max_log_lines: int = Field(
                default=100,
                ge=1,
                le=1000,
                description="Max log lines to return for stream queries (default: 100, max: 1000)",
            ),
            step: Optional[str] = Field(
                default=None,
                description="Step for metric queries (e.g., '30s', '5m'). Auto-computed if omitted.",
            ),
            direction: Optional[str] = Field(
                default=None,
                description="Sort order: 'forward' or 'backward' (default backward)",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID) for multi-tenant Loki",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a LogQL range query returning log streams or metric time-series matrices with cost guardrails. Read-only."""
            query = validate_stream_selector(query)

            warnings: List[str] = []
            hc_labels = detect_high_cardinality_in_selector(query)
            if hc_labels:
                warnings.append(
                    f"High-cardinality labels in stream selector: {hc_labels}."
                )

            s = parse_relative_time(start)
            e = parse_relative_time(end)

            validate_time_window(
                s, e, max_hours=config.guardrails.max_time_window_hours
            )

            try:
                stats = await loki.get_index_stats(query=query, start=s, end=e, org_id=org_id)
                query_bytes = stats.get("bytes", 0)
                if query_bytes > config.guardrails.max_query_bytes:
                    raise LokiQueryTooExpensiveError(
                        f"Query would scan {query_bytes / 1e9:.2f} GB "
                        f"(limit: {config.guardrails.max_query_bytes / 1e9:.1f} GB). "
                        f"Narrow the time range or add more selectors."
                    )
            except LokiQueryTooExpensiveError:
                raise
            except Exception:
                pass

            clamped_limit = min(max_log_lines, config.guardrails.max_log_limit)
            is_metric_q = bool(_METRIC_QUERY_RE.search(query))
            effective_step = step
            if is_metric_q and not effective_step:
                try:
                    win_sec = max(
                        60.0,
                        (_parse_to_datetime(e) - _parse_to_datetime(s)).total_seconds(),
                    )
                    effective_step = f"{max(15, int(win_sec // 60))}s"
                except Exception:
                    effective_step = "60s"

            if ctx:
                await ctx.info(f"Executing range query ({start} → {end})...")

            data = await loki.query_range(
                query=query,
                start=s,
                end=e,
                limit=clamped_limit,
                step=effective_step,
                direction=None if is_metric_q and direction is None else direction,
                org_id=org_id,
            )

            result_type = data.get("resultType", "unknown")
            raw_result = data.get("result", [])

            if result_type == "streams":
                formatted = format_log_entries(
                    raw_result, max_lines=clamped_limit
                )
                total_lines = sum(
                    len(st.get("entries", [])) for st in formatted
                )
                truncated = total_lines >= clamped_limit

                approx_bytes = len(_json.dumps(formatted, ensure_ascii=False))
                payload_truncated = approx_bytes >= _MAX_PAYLOAD_BYTES * 0.95
                if payload_truncated and not truncated:
                    truncated = True

                if ctx:
                    await ctx.info(
                        f"Returned {total_lines} log lines"
                        f"{' (truncated)' if truncated else ''}"
                    )

                return enforce_structured_size_limit(
                    {
                        "result_type": result_type,
                        "streams": formatted,
                        "total_lines": total_lines,
                        "truncated": truncated,
                        "warnings": warnings,
                    },
                    truncatable_key="streams",
                    max_bytes=config.response_size_soft_limit,
                    query_hint=query,
                )

            max_series = config.guardrails.max_series
            max_pts = config.guardrails.max_points_per_series

            total_raw_series = len(raw_result)
            truncated_series: bool = total_raw_series > max_series
            if truncated_series:
                raw_result = raw_result[:max_series]
                warnings.append(
                    f"Result capped at {max_series} series (query returned {total_raw_series})."
                )

            series: List[Dict[str, Any]] = []
            for item in raw_result:
                values: List[Any] = item.get("values", [])
                truncated_pts = len(values) > max_pts
                if truncated_pts:
                    values = values[-max_pts:]
                series.append({
                    "metric": item.get("metric", {}),
                    "values": values,
                    "truncated_points": truncated_pts,
                })

            return enforce_structured_size_limit(
                {
                    "result_type": result_type,
                    "series": series,
                    "total_series": total_raw_series,
                    "truncated_series": truncated_series,
                    "warnings": warnings,
                },
                truncatable_key="series",
                max_bytes=config.response_size_soft_limit,
                query_hint=query,
            )

        # ──────────────────────────────────────────
        # Tool 9: loki_query_a2ui
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            name="loki_query_a2ui",
            annotations=ToolAnnotations(
                title="A2UI Log Table Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_query_a2ui(
            query: str = Field(
                ...,
                min_length=1,
                description="LogQL stream query formatted with '| json' or '| logfmt' and '| line_format' for A2UI table rendering",
            ),
            title: str = Field(..., description="The title for the A2UI log table"),
            start: str = Field(
                default="now-1h",
                description="Start timestamp (RFC3339 or relative like 'now-1h')",
            ),
            end: str = Field(
                default="now",
                description="End timestamp (RFC3339 or relative like 'now')",
            ),
            max_log_lines: int = Field(
                default=100,
                ge=1,
                le=1000,
                description="Max log lines to return (default: 100).",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a LogQL range query and flatten results into an interactive A2UI log table payload. Read-only."""
            query = validate_stream_selector(query)

            s = parse_relative_time(start)
            e = parse_relative_time(end)
            validate_time_window(s, e, max_hours=config.guardrails.max_time_window_hours)

            clamped_limit = min(max_log_lines, config.guardrails.max_log_limit)
            is_metric_a2ui = bool(_METRIC_QUERY_RE.search(query))
            a2ui_step: Optional[str] = None
            if is_metric_a2ui:
                try:
                    win_sec = max(
                        60.0,
                        (_parse_to_datetime(e) - _parse_to_datetime(s)).total_seconds(),
                    )
                    a2ui_step = f"{max(15, int(win_sec // 60))}s"
                except Exception:
                    a2ui_step = "60s"

            if ctx:
                await ctx.info(f"Executing A2UI range query ({start} → {end})...")

            data = await loki.query_range(
                query=query,
                start=s,
                end=e,
                limit=clamped_limit,
                step=a2ui_step,
                direction=None if is_metric_a2ui else "backward",
                org_id=org_id,
            )

            result_type = data.get("resultType", "unknown")
            raw_result = data.get("result", [])

            if result_type != "streams":
                chart_series = []
                max_pts = config.guardrails.max_points_per_series
                for item in raw_result[: config.guardrails.max_series]:
                    vals = item.get("values") or (
                        [item["value"]] if "value" in item else []
                    )
                    chart_series.append(
                        {
                            "metric": item.get("metric", {}),
                            "values": vals[-max_pts:],
                        }
                    )
                return enforce_structured_size_limit(
                    {
                        "title": title,
                        "query": query,
                        "widgetType": "timeseries",
                        "result_type": result_type,
                        "series": chart_series,
                    },
                    truncatable_key="series",
                    max_bytes=config.response_size_soft_limit,
                    query_hint=query,
                )

            log_lines = []
            payload_bytes = 0

            def get_severity(labels: dict) -> str:
                for key in ["level", "severity", "severity_text", "detected_level", "lvl"]:
                    if key in labels and labels[key]:
                        return str(labels[key])
                return "unknown"

            for stream in raw_result:
                labels = stream.get("stream", {})
                sev = get_severity(labels)
                values = stream.get("values", [])

                for entry in values:
                    if len(log_lines) >= clamped_limit:
                        break

                    ts = entry[0] if len(entry) > 0 else ""
                    line_body = entry[1] if len(entry) > 1 else ""

                    if len(line_body) > _MAX_LINE_CHARS:
                        line_body = line_body[:_MAX_LINE_CHARS] + "…[truncated]"

                    log_entry = {
                        "timestamp": ts,
                        "severity": sev,
                        "message": line_body,
                    }

                    entry_bytes = len(_json.dumps(log_entry, ensure_ascii=False))
                    if payload_bytes + entry_bytes > _MAX_PAYLOAD_BYTES:
                        break

                    log_lines.append(log_entry)
                    payload_bytes += entry_bytes

                if len(log_lines) >= clamped_limit or payload_bytes >= _MAX_PAYLOAD_BYTES:
                    break

            a2ui_payload = {
                "title": title,
                "query": query,
                "logLines": log_lines,
            }

            return enforce_structured_size_limit(
                a2ui_payload,
                truncatable_key="logLines",
                max_bytes=config.response_size_soft_limit,
                query_hint=query,
            )
