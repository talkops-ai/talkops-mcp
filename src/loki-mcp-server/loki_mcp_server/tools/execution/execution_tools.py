"""Execution tools — LogQL instant and range query execution.

v4 Tools: execute_logql_instant, execute_logql_query
"""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.exceptions import LokiQueryTooExpensiveError
from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.response_size import enforce_structured_size_limit
from loki_mcp_server.utils.logql_helpers import (
    detect_high_cardinality_in_selector,
    format_log_entries,
    validate_stream_selector,
    _MAX_PAYLOAD_BYTES,
    _MAX_LINE_CHARS,
)
from loki_mcp_server.utils.time_utils import (
    parse_relative_time,
    validate_time_window,
)


class ExecutionTools(BaseTool):
    """LogQL query execution tools.

    These tools actually execute queries against Loki and return
    real log/metric data. All expensive queries should be
    preflight-checked with get_query_stats first.
    """

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all execution tools with the MCP instance."""
        loki = self.loki_service
        config = self.config

        # ──────────────────────────────────────────
        # Tool 7: execute_logql_instant
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Execute LogQL Instant Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def execute_logql_instant(
            query: str = Field(
                ...,
                min_length=1,
                description=(
                    "LogQL query string. CRITICAL: The query MUST contain a stream "
                    "selector wrapped in curly braces {label=\"value\"}. "
                    "CORRECT: '{service_name=\"my-service\"}' or "
                    "'rate({app=\"checkout\"} |= \"error\" [5m])'. "
                    "WRONG: 'service_name=\"my-service\"' (missing braces). "
                    "WRONG: '{{app=\"checkout\"}}' (double braces). "
                    "The curly braces are NOT optional."
                ),
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
            """Execute a point-in-time LogQL query for scalar answers.

            **For quick checks and current-state questions** — evaluates
            a LogQL query at a single timestamp. Best for count, rate,
            avg aggregations that answer "what is the current value?".
            Read-only.

            Returns:
            - {"result_type": "vector"|"streams", "result": [...],
               "warnings": [str]}

            When NOT to use: For time-series or log ranges use
            execute_logql_query. For pre-checking cost use get_query_stats.

            Common errors:
            - High-cardinality label in selector: Warnings returned inline.
            - Empty result: No data at the evaluation timestamp.
            """
            query = validate_stream_selector(query)

            warnings: List[str] = []
            hc_labels = detect_high_cardinality_in_selector(query)
            if hc_labels:
                warnings.append(
                    f"High-cardinality labels in stream selector: {hc_labels}. "
                    f"Move to structured metadata filter or line filter."
                )

            t = parse_relative_time(time) if time else None

            params: Dict[str, Any] = {}
            if limit is not None:
                params["limit"] = min(limit, config.guardrails.max_log_limit)
            if direction:
                params["direction"] = direction

            if ctx:
                await ctx.info(f"Executing instant query...")

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
        # Tool 8: execute_logql_query
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Execute LogQL Range Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def execute_logql_query(
            query: str = Field(
                ...,
                min_length=1,
                description=(
                    "LogQL query string. CRITICAL: The query MUST contain a stream "
                    "selector wrapped in curly braces {label=\"value\"}. "
                    "CORRECT: '{service_name=\"my-service\"}' or "
                    "'{app=\"checkout\"} |= \"error\" | json' or "
                    "'rate({app=\"checkout\"} [5m])'. "
                    "WRONG: 'service_name=\"my-service\"' (missing braces). "
                    "WRONG: '{{app=\"checkout\"}}' (double braces). "
                    "The curly braces are NOT optional."
                ),
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
                description=(
                    "Max log lines to return for stream queries (default: 100, max: 1000). "
                    "Keep low to avoid exceeding MCP context limits."
                ),
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
            """Execute a LogQL range query for log lines or metric time-series.

            **Unified execution tool for all range queries.** Handles
            both log queries (returns streams) and metric queries with
            rate(), count_over_time(), etc. (returns matrix). Includes
            guardrails: time window validation, cardinality checks,
            and cost-based rejection. Read-only.

            Returns (logs):
            - {"result_type": "streams", "streams": [...],
               "total_lines": int, "truncated": bool, "warnings": [str]}

            Returns (metrics):
            - {"result_type": "matrix", "series": [...],
               "total_series": int, "truncated_series": bool,
               "warnings": [str]}

            If `truncated=true` or `truncated_series=true`, results were
            capped. Narrow the time range, add label filters, or increase
            max_log_lines to retrieve more.

            When NOT to use: For instant/scalar queries use
            execute_logql_instant. For pre-checking cost use
            get_query_stats.

            Common errors:
            - Query too expensive: Use get_query_stats first to check cost.
            - Time window too large: Narrow the range (max configurable).
            - High-cardinality label in selector: Move to metadata filter.
            """
            query = validate_stream_selector(query)

            warnings: List[str] = []
            hc_labels = detect_high_cardinality_in_selector(query)
            if hc_labels:
                warnings.append(
                    f"High-cardinality labels in stream selector: {hc_labels}. "
                    f"Move to structured metadata filter or line filter."
                )

            s = parse_relative_time(start)
            e = parse_relative_time(end)

            # Validate time window
            validate_time_window(
                s, e, max_hours=config.guardrails.max_time_window_hours
            )

            # Preflight cost check
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
                # Stats endpoint may not be available — proceed without check
                pass

            # Clamp requested log lines against guardrail ceiling
            clamped_limit = min(max_log_lines, config.guardrails.max_log_limit)

            if ctx:
                await ctx.info(f"Executing range query ({start} → {end})...")

            data = await loki.query_range(
                query=query,
                start=s,
                end=e,
                limit=clamped_limit,
                step=step,
                direction=direction,
                org_id=org_id,
            )

            result_type = data.get("resultType", "unknown")
            raw_result = data.get("result", [])

            # ── Stream (log) response ──────────────────────────────────
            if result_type == "streams":
                formatted = format_log_entries(
                    raw_result, max_lines=clamped_limit
                )
                total_lines = sum(
                    len(s.get("entries", [])) for s in formatted
                )
                # Truncated if the line limit OR the byte budget was hit.
                truncated = total_lines >= clamped_limit

                import json as _json
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

            # ── Matrix (metric) response ───────────────────────────────
            max_series = config.guardrails.max_series
            max_pts = config.guardrails.max_points_per_series

            total_raw_series = len(raw_result)
            truncated_series: bool = total_raw_series > max_series
            if truncated_series:
                raw_result = raw_result[:max_series]
                warnings.append(
                    f"Result capped at {max_series} series "
                    f"(query returned {total_raw_series}). "
                    f"Add more label filters to narrow results."
                )

            series: List[Dict[str, Any]] = []
            for item in raw_result:
                values: List[Any] = item.get("values", [])
                truncated_pts = len(values) > max_pts
                if truncated_pts:
                    values = values[-max_pts:]  # keep the most-recent points
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
                description=(
                    "LogQL query string. CRITICAL: The query MUST contain a stream "
                    "selector wrapped in curly braces {label=\"value\"}. "
                    "CRITICAL FOR A2UI: ALWAYS append `| json` (or `| logfmt`) and `| line_format` "
                    "to extract and display clean parsed fields in the UI! "
                    "CORRECT: '{app=\"checkout\"} | json | line_format \"{{.method}} {{.status}}\"'. "
                ),
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
            """Execute a LogQL range query and format the result for A2UI log tables.

            Use this tool when the coordinator or a subagent needs to render interactive
            log tables directly in the frontend UI. The tool handles query execution,
            truncation, and data flattening into the expected A2UI schema. Read-only.

            Returns:
            - {"title": str, "query": str, "logLines": [{"message": str, "severity": str, "timestamp": str}, ...]}

            When NOT to use: For raw log streams or scalar point-in-time metrics,
            use execute_logql_query or execute_logql_instant instead.

            Common errors:
            - Expected log streams, got matrix: Occurs if the LogQL query returns metrics 
              (e.g., using rate() or count_over_time()). Use execute_logql_query for those.
            - Payload truncated: Occurs if the resulting logs hit the soft byte limit.
              Narrow the time window or add label filters.
            """
            query = validate_stream_selector(query)

            s = parse_relative_time(start)
            e = parse_relative_time(end)
            validate_time_window(s, e, max_hours=config.guardrails.max_time_window_hours)

            clamped_limit = min(max_log_lines, config.guardrails.max_log_limit)

            if ctx:
                await ctx.info(f"Executing A2UI range query ({start} → {end})...")

            data = await loki.query_range(
                query=query,
                start=s,
                end=e,
                limit=clamped_limit,
                org_id=org_id,
            )

            result_type = data.get("resultType", "unknown")
            raw_result = data.get("result", [])
            
            if result_type != "streams":
                return {
                    "title": title,
                    "query": query,
                    "error": f"Expected log streams, got {result_type}. Use prom_query_a2ui_chart or metrics builder for this.",
                }

            # Map to A2UI LogLines
            log_lines = []
            payload_bytes = 0
            
            # Helper for getting severity
            def get_severity(labels: dict) -> str:
                for key in ["level", "severity", "lvl"]:
                    if key in labels:
                        return str(labels[key])
                return "unknown"
                
            import json as _json

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
                        "message": line_body
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
                "logLines": log_lines
            }

            return enforce_structured_size_limit(
                a2ui_payload,
                truncatable_key="logLines",
                max_bytes=config.response_size_soft_limit,
                query_hint=query,
            )


