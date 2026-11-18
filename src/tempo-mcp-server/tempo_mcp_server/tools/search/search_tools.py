"""Tempo trace search, retrieval, factual summarization, and correlation tools."""

import re
from typing import Any, Dict, List, Literal, Optional, Union

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from tempo_mcp_server.exceptions import (
    TempoOperationError,
    TempoQueryError,
    TempoValidationError,
)
from tempo_mcp_server.models.search import SearchFilters, TraceSearchOutput, TraceSearchResult
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.response_size import enforce_structured_size_limit
from tempo_mcp_server.utils.time_helpers import resolve_time_params
from tempo_mcp_server.utils.trace_summarizer import (
    _extract_spans,
    _get_duration_ms,
    _get_span_attr,
    _get_span_start_ns,
    _is_error_status,
    _normalize_id,
    summarize_trace,
)
from tempo_mcp_server.utils.traceql_helpers import (
    apply_query_hints,
    build_traceql_from_filters,
    compute_next_window,
    merge_traceql_queries,
    normalize_traceql_query,
    validate_traceql_basic,
)

_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{16,32}$")


def _validate_trace_id(trace_id: str) -> None:
    """Raise TempoValidationError if trace_id is not valid hex."""
    if not _TRACE_ID_RE.match(trace_id):
        raise TempoValidationError(
            f"Invalid trace ID '{trace_id}': must be 16–32 hexadecimal characters."
        )


def _parse_window(since: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """Parse relative duration ('1h') or epoch range ('1700000000..1700003600')."""
    if since and ".." in since:
        parts = since.split("..", 1)
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return resolve_time_params(since=since)


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

    def add_with_ancestors(sid: str) -> None:
        curr = sid
        while curr and curr not in selected_ids and curr in by_id:
            selected_ids.add(curr)
            curr = parent_map.get(curr, "")

    roots = [sid for sid, pid in parent_map.items() if not pid or pid not in by_id]
    for r in roots:
        add_with_ancestors(r)

    for sid, span in by_id.items():
        is_error = _is_error_status(span)
        if not is_error:
            for event in span.get("events", []):
                if event.get("name") == "exception":
                    is_error = True
                    break
        if is_error:
            add_with_ancestors(sid)

    sorted_spans = sorted(spans, key=lambda s: _get_duration_ms(s), reverse=True)
    for s in sorted_spans:
        if len(selected_ids) >= max_spans:
            break
        sid = _normalize_id(s.get("spanId") or s.get("span_id", ""))
        if sid and sid not in selected_ids:
            add_with_ancestors(sid)

    return [by_id[sid] for sid in selected_ids]


class SearchTools(BaseTool):
    """Trace search, retrieval, factual summarization, and correlation tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("search", is_write=False):
            return

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
                description="TraceQL query selector, e.g. '{ resource.service.name = \"api\" && status = error }'",
            ),
            filters: Optional[Union[SearchFilters, Dict[str, Any]]] = Field(
                default=None,
                description=(
                    "Structured search filters (service, namespace, status, min_duration_ms, "
                    "http_status_gte, leaf_spans_only, min_child_spans, missing_attributes, present_attributes)"
                ),
            ),
            since: Optional[str] = Field(
                default=None,
                description="Relative duration ('1h', '6h') or epoch range ('start..end')",
            ),
            limit: Optional[int] = Field(default=None, description="Max traces to return"),
            spss: Optional[int] = Field(default=None, description="Spans per span-set"),
            most_recent: bool = Field(
                default=False,
                description="Append with(most_recent=true) query hint to prioritize newest matching traces",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Search traces using raw TraceQL and/or structured SearchFilters.

            Returns: {"effective_query": str, "traces": [...], "truncated": bool, "next_window": {...}|null}.
            When NOT to use: For time-series aggregations use tempo_traceql_metrics_range; for known trace_id use tempo_summarize_trace.
            """
            parsed_filters: Optional[SearchFilters] = None
            if isinstance(filters, SearchFilters):
                parsed_filters = filters
            elif isinstance(filters, dict):
                parsed_filters = SearchFilters(**filters)

            generated_query = build_traceql_from_filters(parsed_filters) if parsed_filters else ""
            effective_query = merge_traceql_queries(query, generated_query)

            if effective_query:
                effective_query = normalize_traceql_query(effective_query)

            policy = config.query_policy
            if policy.require_filter_or_query and not effective_query:
                raise TempoValidationError(
                    "At least one filter or TraceQL query is required. "
                    "Provide 'query' or 'filters' (e.g. filters={'service': 'api'})."
                )

            if effective_query:
                error = validate_traceql_basic(effective_query)
                if error:
                    raise TempoQueryError(f"TraceQL validation failed: {error}")
                effective_query = apply_query_hints(effective_query, most_recent=most_recent)

            resolved_start, resolved_end = _parse_window(since)
            if policy.require_time_range and not resolved_start and not since:
                resolved_start, resolved_end = resolve_time_params(since="1h")

            effective_limit = min(limit or policy.default_search_limit, policy.max_search_limit)
            effective_spss = min(spss or policy.default_spss, policy.max_spss)

            try:
                if ctx:
                    await ctx.info(
                        f"Searching backend '{backend_id}' with query: {effective_query or '{}'}..."
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

                raw_traces = result.get("traces", [])
                traces = []
                for t in raw_traces:
                    tid = t.get("traceID", "")
                    traces.append(TraceSearchResult(
                        trace_id=tid,
                        root_service=t.get("rootServiceName"),
                        root_span=t.get("rootTraceName"),
                        start_time=t.get("startTimeUnixNano"),
                        duration_ms=t.get("durationMs"),
                        span_sets_count=len(t.get("spanSets", [])),
                        resource_uri=f"tempo://traces/{backend_id}/{tid}" if tid else None,
                    ).model_dump(exclude_none=True))

                response_metrics = result.get("metrics", {})
                inspected = response_metrics.get("inspectedTraces", 0)
                if inspected and inspected > len(traces):
                    truncated = True
                else:
                    truncated = len(traces) >= effective_limit

                next_window = (
                    compute_next_window(raw_traces, resolved_start, resolved_end)
                    if truncated
                    else None
                )

                output = TraceSearchOutput(
                    effective_query=effective_query or "{}",
                    traces=[],
                    truncated=truncated,
                    total_matched=len(traces),
                    next_window=next_window,
                    metrics=response_metrics or None,
                )
                payload = output.model_dump(exclude_none=True)
                payload["traces"] = traces
                payload["search_metrics"] = response_metrics or None
                return enforce_structured_size_limit(
                    payload,
                    truncatable_key="traces",
                    max_bytes=config.response_size_soft_limit,
                    query_hint=effective_query,
                )
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                self.handle_error(e, "tempo_traceql_search", backend_id=backend_id)
                raise

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
                description="Maximum spans to return when slicing large traces",
            ),
            since: Optional[str] = Field(
                default=None,
                description="Optional time window ('1h' or 'start..end') to bound trace lookup",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Retrieve a trace by ID with optional span-count slicing and time bounds.

            Returns: {"trace_id": str, "format": "llm"|"otlp_json", "trace": {...}, "llm_format_used": bool}.
            When NOT to use: For critical path and error facts, call tempo_summarize_trace.
            """
            _validate_trace_id(trace_id)
            resolved_start, resolved_end = _parse_window(since) if since else (None, None)
            try:
                if ctx:
                    await ctx.info(f"Retrieving trace {trace_id[:16]}...")
                result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    start=resolved_start,
                    end=resolved_end,
                    max_spans=max_spans,
                )
                response: Dict[str, Any] = {
                    "trace_id": trace_id,
                    "format": "llm" if result.get("llm_format_used") else "otlp_json",
                    "trace": result.get("trace", {}),
                    "llm_format_used": result.get("llm_format_used", False),
                }
                for key in ("truncated", "total_spans", "returned_spans", "truncation_note"):
                    if key in result:
                        response[key] = result[key]
                return response
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                self.handle_error(e, "tempo_get_trace", backend_id=backend_id, resource_name=trace_id)
                raise

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
            trace_id: str = Field(..., min_length=16, max_length=32, description="Trace ID (16–32 hex chars)"),
            max_spans: int = Field(default=50, ge=5, le=1000, description="Max spans evaluated for critical path"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Extract factual summary of a trace: critical path, self-time hotspots, errors, and K8s context.

            Returns: {"trace_id": str, "critical_path": [...], "self_time_hotspots": [...], "errors": [...], "deepest_error_span": {...}, "observation_codes": [...]}.
            When NOT to use: For raw span payloads, call tempo_get_trace.
            """
            _validate_trace_id(trace_id)
            try:
                if ctx:
                    await ctx.info(f"Fetching and summarizing trace {trace_id[:16]}...")
                result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    llm_format=False,
                )
                trace_data = result.get("trace", {})
                summary = summarize_trace(trace_id, trace_data, max_spans=max_spans)
                return summary.model_dump()
            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                self.handle_error(e, "tempo_summarize_trace", backend_id=backend_id, resource_name=trace_id)
                raise

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
            correlation_strategy: Literal[
                "same_service_errors",
                "same_endpoint",
                "temporal_neighbors",
                "downstream_cascade",
                "span_links",
            ] = Field(
                default="same_service_errors",
                description="Correlation strategy: same_service_errors, same_endpoint, temporal_neighbors, downstream_cascade, span_links",
            ),
            since: Optional[str] = Field(default="1h", description="Time window to search"),
            limit: Optional[int] = Field(default=5, description="Max related traces to return"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Find traces correlated with a seed trace by error origin, endpoint, time, or cascade.

            Returns: {"seed_trace_id": str, "strategy": str, "related_traces": [...], "effective_query": str}.
            When NOT to use: For arbitrary TraceQL queries, call tempo_traceql_search.
            """
            _validate_trace_id(trace_id)
            try:
                if ctx:
                    await ctx.info(f"Fetching seed trace {trace_id[:16]}...")
                seed_result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    llm_format=False,
                )
                seed_data = seed_result.get("trace", {})
                summary = summarize_trace(trace_id, seed_data)

                correlation_query = ""
                strategy_note: Optional[str] = None

                if correlation_strategy == "same_service_errors":
                    if summary.errors:
                        svc = summary.errors[0].service
                        correlation_query = f'{{ resource.service.name = "{svc}" && status = error }}'
                    else:
                        strategy_note = "No error spans present in seed trace; matched root service instead."
                        if summary.critical_path:
                            svc = summary.critical_path[0].service
                            correlation_query = f'{{ resource.service.name = "{svc}" }}'

                elif correlation_strategy == "same_endpoint":
                    if summary.critical_path:
                        svc = summary.critical_path[0].service
                        span = summary.critical_path[0].span_name
                        correlation_query = f'{{ resource.service.name = "{svc}" && name = "{span}" }}'
                    else:
                        strategy_note = "No critical path spans present in seed trace."

                elif correlation_strategy == "downstream_cascade":
                    if summary.deepest_error_span and summary.critical_path:
                        root_svc = summary.critical_path[0].service
                        leaf_svc = summary.deepest_error_span.service
                        if root_svc != leaf_svc:
                            correlation_query = (
                                f'{{ resource.service.name = "{root_svc}" }} >> '
                                f'{{ resource.service.name = "{leaf_svc}" && status = error }}'
                            )
                        else:
                            correlation_query = f'{{ resource.service.name = "{leaf_svc}" && status = error }}'
                    elif summary.critical_path:
                        svc = summary.critical_path[0].service
                        correlation_query = f'{{ resource.service.name = "{svc}" }}'

                elif correlation_strategy == "temporal_neighbors":
                    if summary.critical_path:
                        svc = summary.critical_path[0].service
                        correlation_query = f'{{ resource.service.name = "{svc}" }}'
                    else:
                        strategy_note = "No spans present in seed trace."

                elif correlation_strategy == "span_links":
                    correlation_query = f'{{ link:traceID = "{trace_id.lower()}" }}'

                if not correlation_query:
                    correlation_query = "{}"

                resolved_start, resolved_end = _parse_window(since or "6h")
                result = await tempo_service.traceql_search(
                    backend_id=backend_id,
                    tenant=tenant,
                    q=correlation_query,
                    start=resolved_start,
                    end=resolved_end,
                    limit=limit or 5,
                )

                seen_tids: set[str] = {trace_id.lower()}
                related: List[Dict[str, Any]] = []

                # Also collect outbound span links embedded directly in the seed trace
                seed_spans = _extract_spans(seed_data)
                outbound_link_tids: List[str] = []
                has_messaging_span = False
                for sp in seed_spans:
                    if _get_span_attr(sp, "messaging.system") or str(sp.get("kind", "")).upper() in ("4", "SPAN_KIND_PRODUCER", "PRODUCER"):
                        has_messaging_span = True
                    for lnk in sp.get("links", []) or []:
                        raw_ltid = lnk.get("traceId") or lnk.get("trace_id", "")
                        norm_ltid = _normalize_id(raw_ltid) if raw_ltid else ""
                        if norm_ltid and norm_ltid not in seen_tids and norm_ltid not in outbound_link_tids:
                            outbound_link_tids.append(norm_ltid)

                # When seed trace is an async producer or span_links was not explicitly selected yet,
                # also check inbound span links ({ link:traceId = "<seed_trace_id>" }) so linked consumers appear first.
                if correlation_strategy != "span_links" and (has_messaging_span or not summary.errors):
                    try:
                        link_res = await tempo_service.traceql_search(
                            backend_id=backend_id,
                            tenant=tenant,
                            q=f'{{ link:traceID = "{trace_id.lower()}" }}',
                            start=resolved_start,
                            end=resolved_end,
                            limit=limit or 5,
                        )
                        for lt in link_res.get("traces", []):
                            ltid = lt.get("traceID", "")
                            if ltid and ltid.lower() not in seen_tids:
                                seen_tids.add(ltid.lower())
                                related.append({
                                    "trace_id": ltid,
                                    "root_service": lt.get("rootServiceName"),
                                    "root_span": lt.get("rootTraceName"),
                                    "duration_ms": lt.get("durationMs"),
                                    "relation": "inbound_span_link",
                                })
                    except Exception:
                        pass

                for out_tid in outbound_link_tids[: (limit or 5)]:
                    try:
                        out_tr = await tempo_service.get_trace(
                            backend_id=backend_id,
                            trace_id=out_tid,
                            tenant=tenant,
                            llm_format=False,
                        )
                        out_sum = summarize_trace(out_tid, out_tr.get("trace", {}))
                        seen_tids.add(out_tid.lower())
                        related.append({
                            "trace_id": out_tid,
                            "root_service": out_sum.critical_path[0].service if out_sum.critical_path else None,
                            "root_span": out_sum.critical_path[0].span_name if out_sum.critical_path else None,
                            "duration_ms": out_sum.total_duration_ms,
                            "relation": "outbound_span_link",
                        })
                    except Exception:
                        pass

                for t in result.get("traces", []):
                    tid_cand = t.get("traceID", "")
                    if tid_cand and tid_cand.lower() not in seen_tids:
                        seen_tids.add(tid_cand.lower())
                        related.append({
                            "trace_id": tid_cand,
                            "root_service": t.get("rootServiceName"),
                            "root_span": t.get("rootTraceName"),
                            "duration_ms": t.get("durationMs"),
                        })
                related = related[: (limit or 5)]

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
                self.handle_error(e, "tempo_find_related_traces", backend_id=backend_id, resource_name=trace_id)
                raise

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
            """Retrieve a trace structured and DAG-pruned for A2UI trace timeline rendering.

            Returns: {"title": str, "traceId": str, "serviceName": str, "spans": [...]}.
            When NOT to use: For text-based trace summarization, call tempo_summarize_trace.
            """
            _validate_trace_id(trace_id)
            try:
                if ctx:
                    await ctx.info(f"Retrieving trace {trace_id[:16]} for A2UI rendering...")

                result = await tempo_service.get_trace(
                    backend_id=backend_id,
                    trace_id=trace_id,
                    tenant=tenant,
                    llm_format=False,
                )

                trace_data = result.get("trace", {})
                raw_spans = _extract_spans(trace_data)
                pruned_spans = prune_trace_spans(raw_spans, max_spans=100)

                a2ui_spans = []
                root_service = "unknown"

                all_norm_ids = {_normalize_id(x.get("spanId") or x.get("span_id", "")) for x in raw_spans}
                for s in pruned_spans:
                    pid = _normalize_id(s.get("parentSpanId") or s.get("parent_span_id", ""))
                    if not pid or pid not in all_norm_ids:
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

                    status_raw = s.get("status", {})
                    code_raw = status_raw.get("code", 0) if isinstance(status_raw, dict) else status_raw
                    if _is_error_status(s):
                        status_str = "error"
                    elif code_raw in (1, "1", "STATUS_CODE_OK", "OK", "ok"):
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

                return {
                    "title": f"Trace: {trace_id}",
                    "traceId": trace_id,
                    "serviceName": root_service,
                    "spans": a2ui_spans,
                }

            except (TempoQueryError, TempoValidationError):
                raise
            except Exception as e:
                raise TempoOperationError(f"Failed to generate A2UI trace {trace_id}: {e}")
