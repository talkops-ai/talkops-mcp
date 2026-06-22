"""TraceQL metrics tools.

Provides range and instant TraceQL metrics queries returning
Prometheus-compatible time series data.
"""

from typing import Any, Dict, List, Optional, Tuple

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions import TempoOperationError, TempoQueryError, TempoValidationError
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.response_size import enforce_structured_size_limit
from tempo_mcp_server.utils.time_helpers import duration_to_seconds, resolve_time_params
from tempo_mcp_server.utils.traceql_helpers import normalize_traceql_query, validate_traceql_basic


def _validate_metrics_time_range(
    start: Optional[float],
    end: Optional[float],
    max_duration_str: str,
) -> None:
    """Pre-validate that the resolved time range doesn't exceed Tempo's max.

    B-02: Tempo's query_frontend.metrics.max_duration (default 3h) rejects
    queries whose time range exceeds the configured ceiling with a 400.
    Validating here gives the AI agent an actionable error instead of a
    raw HTTP error from the backend.

    Raises:
        TempoValidationError if the range exceeds the limit.
    """
    if start is None or end is None:
        return

    try:
        max_seconds = duration_to_seconds(max_duration_str)
    except ValueError:
        # Invalid config — skip client-side validation; Tempo will
        # enforce its own limit and return a clear error if exceeded.
        return

    range_seconds = end - start
    if range_seconds > max_seconds:
        hours = range_seconds / 3600
        max_hours = max_seconds / 3600
        raise TempoValidationError(
            f"Requested time range ({hours:.1f}h) exceeds the maximum allowed "
            f"metrics query duration ({max_hours:.1f}h). "
            f"Tempo's query_frontend.metrics.max_duration is set to {max_duration_str}. "
            f"Either narrow the 'since' parameter to '{max_duration_str}' or less, "
            f"or increase max_duration in the Tempo configuration."
        )


class MetricsTools(BaseTool):
    """TraceQL metrics query tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

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
                description=(
                    "TraceQL metrics query, e.g. "
                    "'{ resource.service.name = \"api\" } | rate()' or "
                    "'{ status = error } | count_over_time()'"
                ),
            ),
            since: Optional[str] = Field(default="1h", description="Relative time range, e.g. '1h', '6h'"),
            start: Optional[float] = Field(default=None, description="Start time as Unix epoch seconds"),
            end: Optional[float] = Field(default=None, description="End time as Unix epoch seconds"),
            step: Optional[str] = Field(default=None, description="Step duration, e.g. '30s', '1m', '5m'"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a TraceQL metrics range query.

            Returns Prometheus-compatible time series data (matrix format).
            Use for RED metrics (rate, errors, duration), trend analysis,
            and SLO calculations. Read-only.

            Supported metrics functions: rate(), count_over_time(), avg_over_time(),
            max_over_time(), min_over_time(), sum_over_time(), quantile_over_time(),
            histogram_over_time().

            Returns:
            - {"effective_query": str, "result_type": "matrix",
               "series": [{"labels": {...}, "points": [{"ts": float, "value": str}]}]}

            When NOT to use: For finding individual traces, use tempo_traceql_search.
            For instant metrics, use tempo_traceql_metrics_instant.

            Common errors:
            - TraceQL metrics requires metrics-generator with local-blocks processor.
              Use tempo_get_diagnostics to verify.
            """
            query = normalize_traceql_query(query)
            error = validate_traceql_basic(query)
            if error:
                raise TempoQueryError(f"TraceQL validation failed: {error}")

            resolved_start, resolved_end = resolve_time_params(start, end, since)

            # B-02: Pre-validate time range against configured max
            max_dur = self.config.query_policy.max_metrics_duration
            _validate_metrics_time_range(resolved_start, resolved_end, max_dur)

            try:
                if ctx:
                    await ctx.info(
                        f"Executing metrics range query on '{backend_id}'..."
                    )
                result = await tempo_service.metrics_query_range(
                    backend_id=backend_id,
                    q=query,
                    tenant=tenant,
                    start=resolved_start,
                    end=resolved_end,
                    step=step,
                )

                # Normalize Prometheus-compatible response
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
                        "points": points,
                    })

                return enforce_structured_size_limit(
                    {
                        "effective_query": query,
                        "result_type": data.get("resultType", "matrix"),
                        "series": series,
                        "stats": result.get("stats"),
                    },
                    truncatable_key="series",
                    max_bytes=self.config.response_size_soft_limit,
                    query_hint=query,
                )
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                # M-01: TempoOperationError is a FastMCP ToolError subclass.
                # FastMCP's dispatcher catches ToolError *before* a bare
                # `except Exception` block runs, so we must intercept it here
                # explicitly to rewrite the "empty ring" 500 into a human-
                # readable structured message.
                err_str = str(e).lower()
                if "maximum allowed duration" in err_str:
                    raise TempoValidationError(
                        f"Tempo rejected the metrics query time range: {e}. "
                        f"The backend's query_frontend.metrics.max_duration "
                        f"limits queries to {max_dur}. Narrow the time range "
                        f"or increase the Tempo-side limit."
                    ) from None
                if "empty ring" in err_str or "generator" in err_str:
                    raise TempoOperationError(
                        "TraceQL metrics-generator is not configured on this Tempo backend. "
                        "Enable the metrics-generator with the 'local-blocks' processor, or "
                        "use tempo_traceql_search for individual trace data instead."
                    ) from None
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
            query: str = Field(
                ..., min_length=1,
                description="TraceQL metrics query for instant evaluation",
            ),
            since: Optional[str] = Field(default="1h", description="Time window to evaluate over"),
            start: Optional[float] = Field(default=None, description="Start time as Unix epoch seconds (overrides since)"),
            end: Optional[float] = Field(default=None, description="End time as Unix epoch seconds (overrides since)"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Execute a TraceQL metrics instant query.

            Returns a point-in-time metrics result (vector format). Read-only.
            Supports both relative (`since`) and absolute (`start`/`end`) time ranges,
            consistent with tempo_traceql_metrics_range.

            Returns:
            - {"effective_query": str, "result_type": "vector",
               "result": [{"metric": {...}, "value": [ts, str_value]}]}

            When NOT to use: For time-series data, use
            tempo_traceql_metrics_range instead.

            Common errors:
            - Same as range queries; requires metrics-generator.
            """
            query = normalize_traceql_query(query)
            error = validate_traceql_basic(query)
            if error:
                raise TempoQueryError(f"TraceQL validation failed: {error}")

            # M-02: respect explicit start/end if provided, fall back to since
            resolved_start, resolved_end = resolve_time_params(start, end, since)

            # B-02: Pre-validate time range against configured max
            max_dur = self.config.query_policy.max_metrics_duration
            _validate_metrics_time_range(resolved_start, resolved_end, max_dur)

            try:
                if ctx:
                    await ctx.info(
                        f"Executing metrics instant query on '{backend_id}'..."
                    )
                result = await tempo_service.metrics_query_instant(
                    backend_id=backend_id,
                    q=query,
                    tenant=tenant,
                    start=resolved_start,
                    end=resolved_end,
                )

                data = result.get("data", result)
                return {
                    "effective_query": query,
                    "result_type": data.get("resultType", "vector"),
                    "result": data.get("result", []),
                }
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                # M-01: Same metrics-generator "empty ring" 500 can come from
                # the instant endpoint too. Explicitly catch and rewrite before
                # FastMCP's ToolError dispatcher intercepts it.
                err_str = str(e).lower()
                if "maximum allowed duration" in err_str:
                    raise TempoValidationError(
                        f"Tempo rejected the metrics query time range: {e}. "
                        f"The backend's query_frontend.metrics.max_duration "
                        f"limits queries to {max_dur}. Narrow the time range "
                        f"or increase the Tempo-side limit."
                    ) from None
                if "empty ring" in err_str or "generator" in err_str:
                    raise TempoOperationError(
                        "TraceQL metrics-generator is not configured on this Tempo backend. "
                        "Enable the metrics-generator with the 'local-blocks' processor, or "
                        "use tempo_traceql_search for individual trace data instead."
                    ) from None
                raise TempoOperationError(f"Metrics instant query failed: {e}") from None

