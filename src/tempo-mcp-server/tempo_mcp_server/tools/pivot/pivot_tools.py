"""Cross-pillar pivot tools.

Provides metrics-to-traces and logs-to-traces correlation.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions import TempoOperationError, TempoValidationError
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.trace_id_extractor import extract_trace_id
from tempo_mcp_server.utils.trace_summarizer import summarize_trace


class PivotTools(BaseTool):
    """Cross-pillar correlation tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        tempo_service = self.tempo_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Exemplar Traces",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_exemplar_traces(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            query: str = Field(
                ..., min_length=1,
                description="TraceQL metrics query to get exemplars from, e.g. '{ status = error } | rate()'",
            ),
            since: Optional[str] = Field(default="1h", description="Time window"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get exemplar trace IDs from a metrics query.

            Pivots from aggregated metrics to concrete traces that contributed
            to those metrics. Useful for drilling into specific exemplars
            behind a metric spike. Read-only.

            Returns:
            - {"trace_candidates": [{"trace_id": str, "timestamp": float, ...}], "total": int}

            When NOT to use: For searching traces by attributes, use
            tempo_traceql_search. For direct trace fetch, use tempo_get_trace.

            Common errors:
            - No exemplars: Exemplars must be enabled in Tempo's metrics-generator.
            """
            from tempo_mcp_server.utils.time_helpers import resolve_time_params

            resolved_start, resolved_end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info("Querying for exemplar traces...")
                result = await tempo_service.metrics_query_range(
                    backend_id=backend_id,
                    q=query,
                    tenant=tenant,
                    start=resolved_start,
                    end=resolved_end,
                    exemplars=True,
                )

                # Extract exemplar trace IDs from response.
                # Per Tempo API: exemplars live at data["exemplars"][], NOT
                # inside each series. A series-level lookup always yields [].
                candidates: List[Dict[str, Any]] = []
                data = result.get("data", result)
                for exemplar in data.get("exemplars", []):
                    trace_id = exemplar.get("traceID", "")
                    if trace_id:
                        candidates.append({
                            "trace_id": trace_id,
                            "source": "exemplar",
                            "timestamp": exemplar.get("timestamp"),
                            "labels": exemplar.get("labels", {}),
                        })

                return {
                    "trace_candidates": candidates,
                    "total": len(candidates),
                }
            except Exception as e:
                raise TempoOperationError(f"Failed to get exemplar traces: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Trace from Log",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_trace_from_log(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            log_line: str = Field(
                ..., min_length=1,
                description="Log line or text containing a trace ID",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Extract a trace ID from a log line and retrieve the trace.

            Parses log text for trace ID patterns (trace_id=, traceId:,
            TraceID=, or standalone 32-char hex), then fetches and summarizes
            the trace. Read-only.

            Returns:
            - {"extracted_trace_id": str|null, "resolved_from": "log_line",
               "trace_summary": {...}|null}

            When NOT to use: If you already have a trace ID, use
            tempo_get_trace or tempo_summarize_trace directly.

            Common errors:
            - No trace ID found: The log line may not contain a parseable trace ID.
            """
            trace_id = extract_trace_id(log_line)
            if not trace_id:
                return {
                    "extracted_trace_id": None,
                    "resolved_from": "log_line",
                    "trace_summary": None,
                    "error": "No trace ID found in the provided text.",
                }

            try:
                if ctx:
                    await ctx.info(f"Found trace ID {trace_id[:16]} in log, fetching...")
                result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    llm_format=False,
                )
                trace_data = result.get("trace", {})
                summary = summarize_trace(trace_id, trace_data)

                return {
                    "extracted_trace_id": trace_id,
                    "resolved_from": "log_line",
                    "trace_summary": summary.model_dump(),
                }
            except Exception as e:
                return {
                    "extracted_trace_id": trace_id,
                    "resolved_from": "log_line",
                    "trace_summary": None,
                    "error": f"Found trace ID '{trace_id}' but failed to retrieve: {e}",
                }
