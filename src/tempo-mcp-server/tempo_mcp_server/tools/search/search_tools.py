"""Tempo trace search and retrieval tools.

Contains the four core search tools including the high-intent
tempo_traceql_search, tempo_summarize_trace, and tempo_find_related_traces.

Note: Search tools use output_schema=None to prevent FastMCP from
auto-generating an outputSchema. This is intentional — trace results
are variable-shape and truncation by the ResponseLimitingMiddleware
would strip structuredContent, breaking client-side outputSchema
validation. The tools still return structured dicts; they just don't
advertise a JSON Schema.
"""

import re
from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

# Trace IDs must be 16-32 hex characters (64-128 bit, zero-padded 128-bit form)
_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{16,32}$")


def _validate_trace_id(trace_id: str) -> None:
    """Raise TempoValidationError if trace_id is not valid hex."""
    if not _TRACE_ID_RE.match(trace_id):
        from tempo_mcp_server.exceptions import TempoValidationError
        raise TempoValidationError(
            f"Invalid trace ID '{trace_id}': must be 16–32 hexadecimal characters."
        )

from tempo_mcp_server.exceptions import (
    TempoOperationError,
    TempoQueryError,
    TempoValidationError,
)
from tempo_mcp_server.models.search import SearchFilters, TraceSearchResult, TraceSearchOutput
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.time_helpers import resolve_time_params
from tempo_mcp_server.utils.traceql_helpers import (
    build_traceql_from_filters,
    merge_traceql_queries,
    normalize_traceql_query,
    validate_traceql_basic,
)
from tempo_mcp_server.utils.response_size import enforce_structured_size_limit
from tempo_mcp_server.utils.trace_summarizer import (
    summarize_trace,
    _extract_spans,
    _normalize_id,
    _get_span_start_ns,
    _get_duration_ms,
    _get_span_attr,
)

def prune_trace_spans(spans: List[Dict[str, Any]], max_spans: int = 100) -> List[Dict[str, Any]]:
    """Smart DAG-aware pruning for trace spans."""
    if len(spans) <= max_spans:
        return spans

    by_id = {}
    parent_map = {}
    for s in spans:
        sid = _normalize_id(s.get("spanId") or s.get("span_id", ""))
        if sid:
            by_id[sid] = s
            pid = _normalize_id(s.get("parentSpanId") or s.get("parent_span_id", ""))
            parent_map[sid] = pid

    selected_ids = set()

    def add_with_ancestors(sid: str):
        curr = sid
        while curr and curr not in selected_ids and curr in by_id:
            selected_ids.add(curr)
            curr = parent_map.get(curr, "")

    # 1. Identify Root
    roots = [sid for sid, pid in parent_map.items() if not pid or pid not in by_id]
    for r in roots:
        add_with_ancestors(r)

    # 2. Identify Errors
    for sid, span in by_id.items():
        is_error = span.get("status", {}).get("code", 0) == 2
        if not is_error:
            for event in span.get("events", []):
                if event.get("name") == "exception":
                    is_error = True
                    break
        if is_error:
            add_with_ancestors(sid)

    # 3. Backfill by duration
    sorted_spans = sorted(spans, key=lambda s: _get_duration_ms(s), reverse=True)
    for s in sorted_spans:
        if len(selected_ids) >= max_spans:
            break
        sid = _normalize_id(s.get("spanId") or s.get("span_id", ""))
        if sid and sid not in selected_ids:
            # We don't want to blow past max_spans by adding a huge ancestor chain,
            # but preserving graph integrity is more important.
            add_with_ancestors(sid)

    return [by_id[sid] for sid in selected_ids]


class SearchTools(BaseTool):
    """Trace search, retrieval, summarization, and correlation tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        tempo_service = self.tempo_service
        config = self.config

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="TraceQL Search",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_traceql_search(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            query: Optional[str] = Field(
                default=None,
                description=(
                    "Raw TraceQL query — MUST be wrapped in { } braces. "
                    "Example: '{ resource.service.name = \"api\" && status = error }'. "
                    "Prefer using structured parameters (service, namespace, status, "
                    "min_duration_ms) instead — they auto-build correct TraceQL."
                ),
            ),
            namespace: Optional[str] = Field(default=None, description="K8s namespace filter"),
            service: Optional[str] = Field(default=None, description="Service name filter"),
            deployment: Optional[str] = Field(default=None, description="K8s deployment filter"),
            cluster: Optional[str] = Field(default=None, description="K8s cluster filter"),
            status: Optional[str] = Field(default=None, description="Status filter: 'error', 'ok', 'unset'"),
            min_duration_ms: Optional[int] = Field(default=None, description="Minimum span duration in ms"),
            max_duration_ms: Optional[int] = Field(default=None, description="Maximum span duration in ms"),
            since: Optional[str] = Field(default=None, description="Relative time range, e.g. '1h', '24h', '7d'"),
            start: Optional[float] = Field(default=None, description="Start time as Unix epoch seconds"),
            end: Optional[float] = Field(default=None, description="End time as Unix epoch seconds"),
            limit: Optional[int] = Field(default=None, description="Max traces to return (default from policy)"),
            spss: Optional[int] = Field(default=None, description="Spans per span-set (detail level)"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Search for traces using TraceQL or K8s-friendly filters.

            HIGH-INTENT: Accepts raw TraceQL OR structured K8s filters (namespace,
            service, deployment), auto-translates to TraceQL, enforces query
            guardrails, and returns compact summaries. Read-only.

            Note: Tempo search is non-deterministic — results may differ between
            calls when matching traces exceed the limit.

            Returns:
            - {"effective_query": str, "traces": [{"trace_id": str, "root_service": str, "duration_ms": int, ...}], "truncated": bool}

            When NOT to use: For a single known trace ID, use tempo_get_trace.
            For TraceQL metrics (rates, counts), use tempo_traceql_metrics_range.

            Common errors:
            - No query or filters: Provide at least a TraceQL query or one filter.
            - Empty results: Broaden time range or relax filters.
            """
            # Build TraceQL from filters
            filters = SearchFilters(
                namespace=namespace, service=service, deployment=deployment,
                cluster=cluster, status=status,
                min_duration_ms=min_duration_ms, max_duration_ms=max_duration_ms,
            )
            generated_query = build_traceql_from_filters(filters)
            effective_query = merge_traceql_queries(query, generated_query)

            # Auto-wrap bare predicates (defense-in-depth for LLM queries
            # that omit the required { } braces)
            if effective_query:
                effective_query = normalize_traceql_query(effective_query)

            # Guardrails
            policy = config.query_policy
            if policy.require_filter_or_query and not effective_query:
                raise TempoValidationError(
                    "At least one filter or TraceQL query is required. "
                    "Provide 'query', 'service', 'namespace', or another filter."
                )

            if effective_query:
                error = validate_traceql_basic(effective_query)
                if error:
                    raise TempoQueryError(f"TraceQL validation failed: {error}")

            # Resolve time
            resolved_start, resolved_end = resolve_time_params(start, end, since)
            if policy.require_time_range and not resolved_start and not since:
                resolved_start, resolved_end = resolve_time_params(since="1h")

            # Apply limits
            effective_limit = min(limit or policy.default_search_limit, policy.max_search_limit)
            effective_spss = min(spss or policy.default_spss, policy.max_spss)

            try:
                if ctx:
                    await ctx.info(
                        f"Searching backend '{backend_id}' with query: "
                        f"{effective_query or '(no filter)'}..."
                    )
                result = await tempo_service.traceql_search(
                    backend_id=backend_id,
                    tenant=tenant,
                    q=effective_query or None,
                    start=resolved_start,
                    end=resolved_end,
                    limit=effective_limit,
                    spss=effective_spss,
                )

                # Normalize response — build via Pydantic to validate schema (L-01)
                raw_traces = result.get("traces", [])
                traces = []
                for t in raw_traces:
                    # L-01: Pydantic constructor validates field types at build time.
                    # A bad value (e.g. duration_ms="not_a_number") raises ValidationError
                    # here rather than silently producing corrupt output.
                    traces.append(TraceSearchResult(
                        trace_id=t.get("traceID", ""),
                        root_service=t.get("rootServiceName"),
                        root_span=t.get("rootTraceName"),
                        start_time=t.get("startTimeUnixNano"),
                        duration_ms=t.get("durationMs"),
                        span_sets_count=len(t.get("spanSets", [])),
                    ).model_dump(exclude_none=True))

                # C-05: Use Tempo's inspectedTraces metadata for authoritative truncation.
                # When inspectedTraces > len(traces), Tempo evaluated more traces than it
                # returned — a definitive signal that results were truncated.
                # Fall back to the heuristic (len >= limit) only when Tempo omits metrics.
                response_metrics = result.get("metrics", {})
                inspected = response_metrics.get("inspectedTraces", 0)
                if inspected and inspected > len(traces):
                    truncated = True   # Authoritative: backend saw more than it returned
                else:
                    truncated = len(traces) >= effective_limit  # Heuristic fallback

                if ctx:
                    await ctx.info(
                        f"Found {len(traces)} traces"
                        f"{' (results truncated)' if truncated else ''}"
                    )

                # L-01: validate the full output payload through the output model too
                output = TraceSearchOutput(
                    effective_query=effective_query or "{}",
                    traces=[],  # already serialized above, pass raw dicts through
                    truncated=truncated,
                    total_matched=len(traces),
                    metrics=response_metrics or None,
                )
                payload = output.model_dump(exclude_none=True)
                payload["traces"] = traces  # re-attach already-validated list
                payload["search_metrics"] = response_metrics or None
                payload["determinism_note"] = (
                    "Tempo search is non-deterministic. Results may differ "
                    "between calls if matching traces exceed the limit."
                )
                return enforce_structured_size_limit(
                    payload,
                    truncatable_key="traces",
                    max_bytes=config.response_size_soft_limit,
                    query_hint=effective_query,
                )
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                raise TempoOperationError(f"Search failed: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Trace by ID",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_trace(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            trace_id: str = Field(..., min_length=16, max_length=32, description="Trace ID (16–32 hex chars)"),
            max_spans: Optional[int] = Field(
                default=None,
                description=(
                    "L-02: Maximum number of spans to return. Large traces (10k+ spans) can "
                    "exceed the 100KB middleware limit. Set this to pre-slice the response "
                    "and receive explicit truncation metadata instead of silent cutoff. "
                    "If omitted, all spans are returned (may hit response size limit)."
                ),
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Retrieve a single trace by ID with LLM-optimized format.

            Attempts the experimental LLM format first for compact, readable
            output. Falls back to standard OTLP JSON if unavailable. Read-only.

            L-02: Use max_spans to avoid silent truncation by the response size
            middleware. When set, returns truncation metadata:
            {"truncated": true, "total_spans": N, "returned_spans": M}.

            Returns:
            - {"trace_id": str, "format": "llm"|"otlp_json", "trace": {...},
               "llm_format_used": bool, ["truncated": bool, "total_spans": int,
               "returned_spans": int, "truncation_note": str]}

            When NOT to use: For analyzing a trace (errors, critical path),
            use tempo_summarize_trace instead. For searching by attributes,
            use tempo_traceql_search.

            Common errors:
            - Trace not found: The trace may have expired or been evicted.
              Verify the trace ID and check retention settings.
            """
            _validate_trace_id(trace_id)  # H-01: reject non-hex IDs early
            try:
                if ctx:
                    await ctx.info(f"Retrieving trace {trace_id[:16]}...")
                result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    max_spans=max_spans,
                )
                response = {
                    "trace_id": trace_id,
                    "format": "llm" if result.get("llm_format_used") else "otlp_json",
                    "trace": result.get("trace", {}),
                    "llm_format_used": result.get("llm_format_used", False),
                }
                # Pass-through truncation metadata from service layer (L-02)
                for key in ("truncated", "total_spans", "returned_spans", "truncation_note"):
                    if key in result:
                        response[key] = result[key]
                return response
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                raise TempoOperationError(f"Failed to retrieve trace {trace_id}: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Summarize Trace",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_summarize_trace(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            trace_id: str = Field(..., min_length=16, max_length=32, description="Trace ID to summarize (16–32 hex chars)"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Generate a server-side intelligent summary of a trace.

            HIGH-INTENT: Fetches trace → extracts critical path → finds errors →
            detects K8s context → generates headline → recommends next queries.
            This is the primary analysis primitive. Read-only.

            Returns:
            - {"trace_id": str, "headline": str, "critical_path": [...],
               "errors": [...], "suspected_root_cause": str|null,
               "recommended_next_queries": [str, ...]}

            When NOT to use: For raw trace data, use tempo_get_trace.
            For searching across traces, use tempo_traceql_search.

            Common errors:
            - Trace not found: Verify the trace ID exists.
            """
            _validate_trace_id(trace_id)  # H-01: reject non-hex IDs early
            try:
                if ctx:
                    await ctx.info(f"Fetching and analyzing trace {trace_id[:16]}...")
                result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    llm_format=False,  # Need OTLP for structural analysis
                )
                trace_data = result.get("trace", {})
                summary = summarize_trace(trace_id, trace_data)
                return summary.model_dump()
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                raise TempoOperationError(f"Failed to summarize trace {trace_id}: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Find Related Traces",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_find_related_traces(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            trace_id: str = Field(..., min_length=16, max_length=32, description="Seed trace ID (16–32 hex chars)"),
            correlation_strategy: str = Field(
                default="same_service_errors",
                description=(
                    "How to find related traces. Options: 'same_service_errors' "
                    "(find errors from same services), 'same_endpoint' (same root span), "
                    "'temporal_neighbors' (traces near same time)."
                ),
            ),
            since: Optional[str] = Field(default="1h", description="Time window to search"),
            limit: Optional[int] = Field(default=5, description="Max related traces to return"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Find traces related to a seed trace using correlation strategies.

            HIGH-INTENT: Fetches the seed trace → extracts key attributes →
            constructs a correlation query → returns matching traces.
            One high-level call replaces manual multi-step correlation. Read-only.

            Returns:
            - {"seed_trace_id": str, "strategy": str, "related_traces": [...],
               "effective_query": str}

            When NOT to use: For direct TraceQL queries, use tempo_traceql_search.

            Common errors:
            - No related traces found: Try a different strategy or broader time range.
            """
            _validate_trace_id(trace_id)  # H-01: reject non-hex IDs early
            try:
                # Step 1: Fetch and summarize seed trace
                if ctx:
                    await ctx.info(f"Fetching seed trace {trace_id[:16]}...")
                seed_result = await tempo_service.get_trace(
                    backend_id=backend_id, trace_id=trace_id,
                    tenant=tenant, llm_format=False,
                )
                seed_data = seed_result.get("trace", {})
                summary = summarize_trace(trace_id, seed_data)

                # Step 2: Build correlation query based on strategy.
                # C-04: Each strategy returns an explicit message when its
                # prerequisites aren't met rather than silently falling through.
                correlation_query = ""
                strategy_note: Optional[str] = None

                if correlation_strategy == "same_service_errors":
                    if summary.errors:
                        svc = summary.errors[0].service
                        correlation_query = f'{{ resource.service.name = "{svc}" && status = error }}'
                    else:
                        strategy_note = (
                            "No errors found in the seed trace. "
                            "Try 'same_endpoint' or 'temporal_neighbors' strategy."
                        )
                        # Fall back to same root service to return something useful
                        if summary.critical_path:
                            svc = summary.critical_path[0].service
                            correlation_query = f'{{ resource.service.name = "{svc}" }}'

                elif correlation_strategy == "same_endpoint":
                    if summary.critical_path:
                        svc = summary.critical_path[0].service
                        span = summary.critical_path[0].span_name
                        correlation_query = f'{{ resource.service.name = "{svc}" && name = "{span}" }}'
                    else:
                        strategy_note = (
                            "No critical path spans found in the seed trace. "
                            "Try 'temporal_neighbors' strategy."
                        )

                elif correlation_strategy == "temporal_neighbors":
                    if summary.critical_path:
                        svc = summary.critical_path[0].service
                        correlation_query = f'{{ resource.service.name = "{svc}" }}'
                    else:
                        strategy_note = (
                            "No spans found in the seed trace — cannot determine root service."
                        )

                else:
                    strategy_note = (
                        f"Unknown strategy '{correlation_strategy}'. "
                        "Valid options: 'same_service_errors', 'same_endpoint', 'temporal_neighbors'."
                    )
                    if summary.critical_path:
                        svc = summary.critical_path[0].service
                        correlation_query = f'{{ resource.service.name = "{svc}" }}'

                if not correlation_query:
                    correlation_query = "{}"

                # Step 3: Search for related traces
                resolved_start, resolved_end = resolve_time_params(since=since)
                result = await tempo_service.traceql_search(
                    backend_id=backend_id, tenant=tenant,
                    q=correlation_query,
                    start=resolved_start, end=resolved_end,
                    limit=limit or 5,
                )

                # Exclude the seed trace itself
                related = [
                    {
                        "trace_id": t.get("traceID", ""),
                        "root_service": t.get("rootServiceName"),
                        "root_span": t.get("rootTraceName"),
                        "duration_ms": t.get("durationMs"),
                    }
                    for t in result.get("traces", [])
                    if t.get("traceID", "").lower() != trace_id.lower()
                ]

                result_payload: Dict[str, Any] = {
                    "seed_trace_id": trace_id,
                    "strategy": correlation_strategy,
                    "related_traces": related,
                    "effective_query": correlation_query,
                    "total_found": len(related),
                }
                if strategy_note:
                    result_payload["strategy_note"] = strategy_note
                return result_payload
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                raise TempoOperationError(f"Failed to find related traces: {e}")

        @mcp_instance.tool(
            name="tempo_query_a2ui",
            annotations=ToolAnnotations(
                title="Query Trace for A2UI Timeline",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_query_a2ui(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            trace_id: str = Field(..., min_length=16, max_length=32, description="Trace ID (16–32 hex chars)"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Retrieve a trace heavily optimized and structured for A2UI rendering.
            
            HIGH-INTENT: Fetches trace, extracts spans, prunes the DAG to fit within
            payload limits while preserving critical errors and parent/child relationships,
            and formats it exactly for the A2UI trace timeline component.

            Returns JSON schema containing: title, traceId, serviceName, and spans[].
            """
            _validate_trace_id(trace_id)
            try:
                if ctx:
                    await ctx.info(f"Retrieving trace {trace_id[:16]} for A2UI rendering...")
                
                result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    llm_format=False,  # Need raw OTLP for span structure
                )
                
                trace_data = result.get("trace", {})
                raw_spans = _extract_spans(trace_data)
                pruned_spans = prune_trace_spans(raw_spans, max_spans=100)
                
                a2ui_spans = []
                root_service = "unknown"
                
                # First pass to find root service
                for s in pruned_spans:
                    sid = _normalize_id(s.get("spanId") or s.get("span_id", ""))
                    pid = _normalize_id(s.get("parentSpanId") or s.get("parent_span_id", ""))
                    # Check if root
                    if not pid or pid not in [_normalize_id(x.get("spanId") or x.get("span_id", "")) for x in raw_spans]:
                        svc = _get_span_attr(s, "service.name") or s.get("_resource_attrs", {}).get("service.name", "unknown")
                        if svc != "unknown":
                            root_service = str(svc)
                            break
                            
                for s in pruned_spans:
                    sid = _normalize_id(s.get("spanId") or s.get("span_id", ""))
                    pid = _normalize_id(s.get("parentSpanId") or s.get("parent_span_id", ""))
                    op_name = s.get("name", "unknown")
                    svc_name = _get_span_attr(s, "service.name") or s.get("_resource_attrs", {}).get("service.name", "unknown")
                    
                    start_time_ns = _get_span_start_ns(s)
                    start_time_ms = int(start_time_ns / 1_000_000) if start_time_ns > 0 else 0
                    
                    duration_ms = _get_duration_ms(s)
                    
                    status_code = s.get("status", {}).get("code", 0)
                    if status_code == 2:
                        status_str = "error"
                    elif status_code == 1:
                        status_str = "ok"
                    else:
                        status_str = "unset"
                        
                    if status_str != "error":
                        for event in s.get("events", []):
                            if event.get("name") == "exception":
                                status_str = "error"
                                break
                                
                    a2ui_spans.append({
                        "spanId": sid,
                        "parentSpanId": pid,
                        "operationName": op_name,
                        "serviceName": str(svc_name),
                        "startTime": start_time_ms,
                        "duration": duration_ms,
                        "status": status_str,
                    })
                    
                a2ui_payload = {
                    "title": f"Trace: {trace_id}",
                    "traceId": trace_id,
                    "serviceName": root_service,
                    "spans": a2ui_spans
                }
                
                # This explicitly bypasses the response limiting middleware via structure,
                # as the middleware A2UI bypass intercepts this exact signature.
                # However we still return the dict.
                return a2ui_payload
                
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                raise TempoOperationError(f"Failed to generate A2UI trace {trace_id}: {e}")
