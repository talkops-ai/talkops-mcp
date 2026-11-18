"""Cross-pillar pivot tools (metrics exemplars and log/W3C traceparent to trace)."""

import json
from typing import Any, Dict, List, Optional, Union

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.time_helpers import resolve_time_params
from tempo_mcp_server.utils.trace_id_extractor import extract_trace_context
from tempo_mcp_server.utils.trace_summarizer import summarize_trace


class PivotTools(BaseTool):
    """Cross-pillar correlation tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("diagnostics", is_write=False):
            return

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
                description="TraceQL metrics query to fetch exemplars from, e.g. '{ status = error } | rate()'",
            ),
            since: Optional[str] = Field(default="1h", description="Time window"),
            limit: int = Field(default=20, ge=1, le=100, description="Max exemplar candidates to return"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Extract exemplar trace IDs from a TraceQL metrics range query.

            Returns: {"trace_candidates": [{"trace_id": str, "timestamp": float, "labels": {...}}], "total": int}.
            When NOT to use: For attribute-based trace search, call tempo_traceql_search.
            """
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
                    step="60s",
                    exemplars=True,
                )

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
                    if len(candidates) >= limit:
                        break

                # When local-blocks exemplar buckets are empty (e.g. un-cut WAL or sparse buckets),
                # supplement trace_candidates from the TraceQL selector part via traceql_search.
                if not candidates and "{" in query and "}" in query:
                    selector_part = query.split("|", 1)[0].strip()
                    if selector_part:
                        try:
                            sr = await tempo_service.traceql_search(
                                backend_id=backend_id,
                                tenant=tenant,
                                q=selector_part,
                                start=resolved_start,
                                end=resolved_end,
                                limit=min(limit, 20),
                            )
                            for tr in sr.get("traces", [])[:limit]:
                                tid = tr.get("traceID", "")
                                if tid:
                                    ts_ns = tr.get("startTimeUnixNano")
                                    candidates.append({
                                        "trace_id": tid,
                                        "source": "exemplar_search_fallback",
                                        "timestamp": (int(ts_ns) / 1e9) if ts_ns else None,
                                        "labels": {
                                            "rootServiceName": tr.get("rootServiceName", ""),
                                            "rootTraceName": tr.get("rootTraceName", ""),
                                            "durationMs": tr.get("durationMs"),
                                        },
                                    })
                        except Exception:
                            pass

                return {
                    "trace_candidates": candidates,
                    "total": len(candidates),
                }
            except Exception as e:
                self.handle_error(e, "tempo_get_exemplar_traces", backend_id=backend_id)
                raise

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
            log_line: Union[str, Dict[str, Any]] = Field(
                ...,
                description="Log line, JSON entry, or W3C traceparent header containing a trace ID",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Extract a trace ID (W3C traceparent, JSON, logfmt, or hex32) from text and summarize the trace.

            Returns: {"extracted_trace_id": str|null, "extracted_span_id": str|null, "format": str|null, "trace_summary": {...}|null}.
            When NOT to use: If trace_id is already known, call tempo_summarize_trace directly.
            """
            raw_log_text = json.dumps(log_line) if isinstance(log_line, dict) else str(log_line)
            extracted = extract_trace_context(raw_log_text)
            trace_id = extracted.get("trace_id")
            if not trace_id:
                return {
                    "extracted_trace_id": None,
                    "extracted_span_id": None,
                    "format": None,
                    "resolved_from": "log_line",
                    "trace_summary": None,
                    "error": "No valid non-zero trace ID found in the provided text.",
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
                    "extracted_span_id": extracted.get("span_id"),
                    "format": extracted.get("format"),
                    "resolved_from": "log_line",
                    "trace_summary": summary.model_dump(),
                }
            except Exception as e:
                return {
                    "extracted_trace_id": trace_id,
                    "extracted_span_id": extracted.get("span_id"),
                    "format": extracted.get("format"),
                    "resolved_from": "log_line",
                    "trace_summary": None,
                    "error": f"Found trace ID '{trace_id}' but failed to retrieve: {e}",
                }
