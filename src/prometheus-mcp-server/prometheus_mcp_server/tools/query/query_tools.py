"""Prometheus PromQL query tools.

Provides granular tools for PromQL validation, instant queries,
range queries, and metric label topology exploration.

Note: Query tools use output_schema=None to prevent FastMCP from
auto-generating an outputSchema. This is intentional — query results
are variable-shape (vector, scalar, matrix) and truncation would
break rigid schema validation on the client side. The tools still
return structured dicts; they just don't advertise a JSON Schema.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool
from prometheus_mcp_server.utils.response_size import enforce_structured_size_limit
from prometheus_mcp_server.utils.compact import compact_instant_result, compact_range_result


class QueryTools(BaseTool):
    """PromQL query execution and validation tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        prometheus_service = self.prometheus_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Validate PromQL",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def prom_validate_promql(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            query: str = Field(..., min_length=1, description="PromQL query string to validate"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Check PromQL syntax before executing.

            Use this first for user-provided queries to catch syntax errors
            before running instant or range queries. Read-only.

            Returns:
            - {\"valid\": bool, \"error\": str|null}

            When NOT to use: For executing queries, use prom_query_instant
            or prom_query_range instead.

            Common errors:
            - Backend unreachable: Check prom://system/backends resource to verify connectivity.
            """
            try:
                result = await prometheus_service.validate_query(backend_id, query)
                return result.model_dump()
            except Exception as e:
                raise PrometheusOperationError(f"Validation failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Instant PromQL Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def prom_query_instant(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            query: str = Field(..., min_length=1, description="PromQL query string"),
            time: Optional[float] = Field(default=None, description="Unix timestamp for query (defaults to now)"),
            timeout: Optional[str] = Field(default=None, description="Query timeout (e.g. '10s', '30s')"),
            allow_raw_counters: bool = Field(default=False, description="Allow raw counter queries without rate()/increase()"),
            max_samples: int = Field(default=500, ge=1, le=5000, description="Max samples to return (default: 500). Increase only if needed; large values risk exceeding context limits."),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a point-in-time PromQL query with counter enforcement.

            Use this for current-state queries (e.g. "what is the value of X now?").
            Enforces semantic counter rules — counters must use rate()/increase().
            Read-only.

            Returns:
            - {"resultType": "vector", "result": [{"metric": {...}, "value": [ts, val]}, ...], "truncated": bool, "truncated_at": int|null}

            If `truncated=true`, the result was capped at `max_samples`. Refine the
            query with label filters or increase max_samples to retrieve more results.

            When NOT to use: For time-range queries, use prom_query_range.
            For syntax validation only, use prom_validate_promql.

            Common errors:
            - Counter enforcement: Raw counter queries are blocked by default.
              Set allow_raw_counters=true to bypass.
            - Invalid syntax (400 Bad Request): Remember that label matchers MUST be enclosed in curly braces if no metric name is provided (e.g., use `{service="cart"}` instead of `service="cart"`).
            - Backend unreachable: Check prom://system/backends resource to verify connectivity.
            """
            try:
                await prometheus_service.enforce_counter_rule(
                    backend_id, query, allow_raw_counters
                )
                result = await prometheus_service.instant_query(
                    backend_id, query, ts=time, timeout=timeout, max_samples=max_samples
                )
                
                # Compact labels and values before size enforcement
                compacted = compact_instant_result(
                    result.model_dump(), query=query
                )
                
                return enforce_structured_size_limit(
                    compacted,
                    truncatable_key="result",
                    max_bytes=self.config.response_size_soft_limit,
                    query_hint=query,
                )
            except ValueError as e:
                raise PrometheusOperationError(str(e))
            except Exception as e:
                raise PrometheusOperationError(f"Instant query failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Range PromQL Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def prom_query_range(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            query: str = Field(..., min_length=1, description="PromQL query string"),
            start: float = Field(..., description="Range start timestamp (Unix epoch)"),
            end: float = Field(..., description="Range end timestamp (Unix epoch)"),
            step: Optional[str] = Field(default=None, description="Step duration, e.g. '30s', '5m' (auto-computed if omitted)"),
            max_points_per_series: int = Field(default=200, description="Max data points per series (default: 200)"),
            timeout: Optional[str] = Field(default=None, description="Query timeout (e.g. '10s', '30s')"),
            allow_raw_counters: bool = Field(default=False, description="Allow raw counter queries without rate()/increase()"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a time-range PromQL query with automatic downsampling.

            Use this for historical/trend queries. Enforces mandatory downsampling
            (100-200 points/series) to protect LLM context windows. Read-only.

            Returns:
            - {\"resultType\": \"matrix\", \"result\": [{\"metric\": {...}, \"values\": [[ts, val], ...]}, ...]}

            When NOT to use: For point-in-time queries, use prom_query_instant.

            Common errors:
            - Counter enforcement: Raw counter queries are blocked by default.
            - Invalid syntax (400 Bad Request): Remember that label matchers MUST be enclosed in curly braces if no metric name is provided (e.g., use `{service="cart"}` instead of `service="cart"`).
            - Invalid PromQL: Use prom_validate_promql first to check syntax.
            """
            try:
                await prometheus_service.enforce_counter_rule(
                    backend_id, query, allow_raw_counters
                )

                # Auto-compute step if not provided
                effective_step = step
                if not effective_step:
                    duration = end - start
                    step_seconds = max(int(duration / max_points_per_series), 15)
                    effective_step = f"{step_seconds}s"

                result = await prometheus_service.range_query(
                    backend_id, query, start, end, effective_step,
                    max_points_per_series=max_points_per_series,
                    timeout=timeout,
                )
                
                range_dict = {
                    "series": [s.model_dump() for s in result.series],
                    "downsampling": result.downsampling.model_dump(),
                    "truncated": result.truncated,
                    "truncated_at": result.truncated_at,
                }
                
                # Compact labels and values before size enforcement
                compacted = compact_range_result(range_dict, query=query)
                
                return enforce_structured_size_limit(
                    compacted,
                    truncatable_key="series",
                    max_bytes=self.config.response_size_soft_limit,
                    query_hint=query,
                )
            except ValueError as e:
                raise PrometheusOperationError(str(e))
            except Exception as e:
                raise PrometheusOperationError(f"Range query failed: {e}")

        @mcp_instance.tool(
            name="prom_query_a2ui_chart",
            annotations=ToolAnnotations(
                title="A2UI Chart PromQL Query",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def prom_query_a2ui_chart(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            query: str = Field(..., min_length=1, description="PromQL query string"),
            start: float = Field(..., description="Range start timestamp (Unix epoch)"),
            end: float = Field(..., description="Range end timestamp (Unix epoch)"),
            title: str = Field(..., description="The title for the A2UI chart"),
            chart_type: str = Field(default="line", description="The chart type (line, bar, area)"),
            y_axis_label: str = Field(default="Value", description="The Y-axis label for the chart"),
            step: Optional[str] = Field(default=None, description="Step duration, e.g. '30s', '5m' (auto-computed if omitted)"),
            max_points_per_series: int = Field(default=200, description="Max data points per series (default: 200)"),
            timeout: Optional[str] = Field(default=None, description="Query timeout (e.g. '10s', '30s')"),
            allow_raw_counters: bool = Field(default=False, description="Allow raw counter queries without rate()/increase()"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a time-range PromQL query and return data formatted for A2UI dynamic components.

            Use this when the coordinator or subagent needs to render a chart directly in the UI.
            Automatically downsamples and formats the output into the A2UI schema. Read-only.

            Returns:
            - {\"title\": \"...\", \"chartType\": \"...\", \"yAxisLabel\": \"...\", \"query\": \"...\", \"timeRange\": {...}, \"series\": [{\"name\": \"...\", \"data\": [{\"x\": ts, \"y\": val}, ...]}, ...]}

            When NOT to use: For point-in-time queries, use prom_query_instant. For raw JSON matrix data without A2UI formatting, use prom_query_range.

            Common errors:
            - Counter enforcement: Raw counter queries are blocked by default.
            - Invalid syntax (400 Bad Request): Remember that label matchers MUST be enclosed in curly braces if no metric name is provided (e.g., use `{service="cart"}` instead of `service="cart"`).
            - Invalid PromQL: Use prom_validate_promql first to check syntax.
            """
            try:
                await prometheus_service.enforce_counter_rule(
                    backend_id, query, allow_raw_counters
                )

                # Auto-compute step if not provided
                effective_step = step
                if not effective_step:
                    duration = end - start
                    step_seconds = max(int(duration / max_points_per_series), 15)
                    effective_step = f"{step_seconds}s"

                result = await prometheus_service.range_query(
                    backend_id, query, start, end, effective_step,
                    max_points_per_series=max_points_per_series,
                    timeout=timeout,
                )

                # Format for A2UI
                series_out = []
                for s in result.series:
                    metric = dict(s.metric)
                    metric_name = metric.pop("__name__", "Series")

                    # Create a display name from labels if available
                    if metric:
                        labels_str = ", ".join([f'{k}="{v}"' for k, v in metric.items()])
                        display_name = f"{{{labels_str}}}"
                    else:
                        display_name = metric_name

                    data_points = []
                    for v in s.values:
                        try:
                            # v[0] is timestamp (already float/int), v[1] is value string
                            ts_ms = int(v[0] * 1000)

                            # Compact value similar to compact_range_result
                            val_str = v[1]
                            f_val = float(val_str)
                            if f_val == int(f_val) and abs(f_val) < 1e15:
                                y_val = float(int(f_val))
                            else:
                                y_val = float(f"{f_val:.6g}")

                            data_points.append({"x": ts_ms, "y": y_val})
                        except (ValueError, TypeError):
                            continue

                    series_out.append({
                        "name": display_name,
                        "data": data_points
                    })

                start_iso = datetime.fromtimestamp(start, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                end_iso = datetime.fromtimestamp(end, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

                a2ui_payload = {
                    "title": title,
                    "chartType": chart_type,
                    "yAxisLabel": y_axis_label,
                    "query": query,
                    "timeRange": {
                        "start": start_iso,
                        "end": end_iso
                    },
                    "series": series_out
                }

                # Enforce size limits on the series list
                return enforce_structured_size_limit(
                    a2ui_payload,
                    truncatable_key="series",
                    max_bytes=self.config.response_size_soft_limit,
                    query_hint=query,
                )

            except ValueError as e:
                raise PrometheusOperationError(str(e))
            except Exception as e:
                raise PrometheusOperationError(f"A2UI chart query failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Explore Metric Labels",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def prom_explore_labels(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            metric_name: str = Field(..., min_length=1, description="Metric name to explore"),
            max_values_per_label: int = Field(default=50, description="Max values to return per label (default: 50, capped to avoid large payloads)"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Discover label names and top values for a given metric.

            Use this to understand metric dimensionality before writing queries.
            Read-only.

            Returns:
            - {\"labels\": {\"label_name\": [\"value1\", ...]}}

            When NOT to use: For executing queries, use prom_query_instant or
            prom_query_range. For the full metric catalog, use the
            prom://metadata/catalog resource.

            Common errors:
            - Metric not found: Verify metric exists via prom://metadata/catalog.
            """
            try:
                result = await prometheus_service.explore_label_topology(
                    backend_id, metric_name, max_values_per_label
                )
                return result.model_dump()
            except Exception as e:
                raise PrometheusOperationError(f"Label exploration failed: {e}")
