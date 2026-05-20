"""Prometheus PromQL query tools.

Provides granular tools for PromQL validation, instant queries,
range queries, and metric label topology exploration.
"""

import time
from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool


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
            )
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
            )
        )
        async def prom_query_instant(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            query: str = Field(..., min_length=1, description="PromQL query string"),
            time: Optional[float] = Field(default=None, description="Unix timestamp for query (defaults to now)"),
            timeout: Optional[str] = Field(default=None, description="Query timeout (e.g. '10s', '30s')"),
            allow_raw_counters: bool = Field(default=False, description="Allow raw counter queries without rate()/increase()"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a point-in-time PromQL query with counter enforcement.

            Use this for current-state queries (e.g. \"what is the value of X now?\").
            Enforces semantic counter rules — counters must use rate()/increase().
            Read-only.

            Returns:
            - {\"resultType\": \"vector\", \"result\": [{\"metric\": {...}, \"value\": [ts, val]}, ...]}

            When NOT to use: For time-range queries, use prom_query_range.
            For syntax validation only, use prom_validate_promql.

            Common errors:
            - Counter enforcement: Raw counter queries are blocked by default.
              Set allow_raw_counters=true to bypass.
            - Backend unreachable: Check prom://system/backends resource to verify connectivity.
            """
            try:
                await prometheus_service.enforce_counter_rule(
                    backend_id, query, allow_raw_counters
                )
                result = await prometheus_service.instant_query(
                    backend_id, query, ts=time, timeout=timeout
                )
                return result.model_dump()
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
            )
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
                return {
                    "series": [s.model_dump() for s in result.series],
                    "downsampling": result.downsampling.model_dump(),
                }
            except ValueError as e:
                raise PrometheusOperationError(str(e))
            except Exception as e:
                raise PrometheusOperationError(f"Range query failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Explore Metric Labels",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_explore_labels(
            backend_id: str = Field(..., min_length=1, description="Prometheus backend ID"),
            metric_name: str = Field(..., min_length=1, description="Metric name to explore"),
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
                    backend_id, metric_name
                )
                return result.model_dump()
            except Exception as e:
                raise PrometheusOperationError(f"Label exploration failed: {e}")
