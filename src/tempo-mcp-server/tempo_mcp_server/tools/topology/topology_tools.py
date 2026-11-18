"""Tempo service topology / dependency mapping tool."""

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.time_helpers import resolve_time_params
from tempo_mcp_server.utils.trace_summarizer import (
    _extract_spans,
    _get_duration_ms,
    _get_span_attr,
    _is_error_status,
    _normalize_id,
)


def extract_dag_service_edges_from_traces(
    traces_data: List[Dict[str, Any]],
    focus_service: Optional[str] = None,
) -> tuple[set[str], List[Dict[str, Any]]]:
    """Extract parent_service -> child_service call edges and latency/error stats from raw OTLP traces."""
    nodes: set[str] = set()
    edge_stats: Dict[tuple[str, str], Dict[str, Any]] = {}

    for trace_obj in traces_data:
        spans = _extract_spans(trace_obj)
        by_id: Dict[str, Dict[str, Any]] = {}
        svc_by_id: Dict[str, str] = {}

        for s in spans:
            raw_sid = s.get("spanId") or s.get("span_id", "")
            sid = _normalize_id(raw_sid) if raw_sid else ""
            svc = (
                _get_span_attr(s, "service.name")
                or s.get("_resource_attrs", {}).get("service.name")
            )
            if svc:
                nodes.add(str(svc))
            if sid:
                by_id[sid] = s
                if svc:
                    svc_by_id[sid] = str(svc)

        for sid, span in by_id.items():
            child_svc = svc_by_id.get(sid)
            raw_parent = span.get("parentSpanId") or span.get("parent_span_id", "")
            pid = _normalize_id(raw_parent) if raw_parent else ""
            parent_svc = svc_by_id.get(pid) if pid else None

            # Also check span.peer.service / span.server.address / db / messaging on client spans
            if not parent_svc or parent_svc == child_svc:
                peer = (
                    _get_span_attr(span, "peer.service")
                    or _get_span_attr(span, "peer.service.name")
                    or _get_span_attr(span, "server.address")
                    or _get_span_attr(span, "net.peer.name")
                    or _get_span_attr(span, "db.system")
                    or _get_span_attr(span, "db.system.name")
                    or _get_span_attr(span, "messaging.system")
                )
                if child_svc and peer and str(peer) != child_svc:
                    parent_svc = child_svc
                    child_svc = str(peer)
                    nodes.add(child_svc)

            if parent_svc and child_svc and parent_svc != child_svc:
                if focus_service and focus_service not in (parent_svc, child_svc):
                    continue
                key = (parent_svc, child_svc)
                st = edge_stats.setdefault(key, {"count": 0, "errors": 0, "durations": []})
                st["count"] += 1
                if _is_error_status(span):
                    st["errors"] += 1
                dur = _get_duration_ms(span)
                if dur > 0:
                    st["durations"].append(dur)

    edges: List[Dict[str, Any]] = []
    for (client_svc, server_svc), st in sorted(edge_stats.items()):
        durs = sorted(st["durations"])
        p95 = durs[min(len(durs) - 1, int(len(durs) * 0.95))] if durs else None
        count = st["count"]
        err_ratio = round(st["errors"] / count, 4) if count > 0 else 0.0
        edges.append({
            "client": client_svc,
            "server": server_svc,
            "sampled_call_count": count,
            "error_rate": err_ratio,
            "p95_duration_ms": round(p95, 2) if p95 is not None else None,
            "source": "trace_dag_sample",
        })

    return nodes, edges


class TopologyTools(BaseTool):
    """Service topology and dependency mapping tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("diagnostics", is_write=False):
            return

        tempo_service = self.tempo_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Service Dependencies",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_service_dependencies(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            since: Optional[str] = Field(default="1h", description="Time window to analyze"),
            service: Optional[str] = Field(
                default=None,
                description="Optional service name to filter upstream/downstream edges",
            ),
            sample_traces: int = Field(
                default=10,
                ge=0,
                le=50,
                description="Max traces to sample for DAG edge extraction fallback when metrics edges are empty",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Discover service nodes and client->server call edges via Prometheus service-graphs, TraceQL metrics, or trace DAG sampling.

            Returns: {"nodes": [{"service": str}], "edges": [{"client": str, "server": str, "source": str, ...}], "source_used": str, "method": str}.
            When NOT to use: For single-trace waterfall inspection, call tempo_summarize_trace.
            """
            resolved_start, resolved_end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info(f"Mapping service dependencies from '{backend_id}'...")
                nodes_set: set[str] = set()
                edges: List[Dict[str, Any]] = []
                method = "service_enumeration"
                source_used = "traceql_search"
                traceql_metrics_ok = False

                # Tier 0 / Primary: Precomputed Prometheus service-graph metrics when configured
                if hasattr(tempo_service, "query_prometheus_service_graphs"):
                    try:
                        p_nodes, p_edges = await tempo_service.query_prometheus_service_graphs(
                            backend_id=backend_id,
                            window=since or "1h",
                            focus_service=service,
                            tenant=tenant,
                        )
                        if p_edges:
                            nodes_set.update(p_nodes)
                            edges.extend(p_edges)
                            method = "prometheus_service_graphs"
                            source_used = "prometheus"
                    except Exception:
                        pass

                # Attempt 1: Valid TraceQL metrics query with required | rate() aggregator
                if not edges:
                    try:
                        if service:
                            structural_tql = (
                                f'{{ resource.service.name = "{service}" }} >> {{ }}'
                                f' | rate() by (resource.service.name, span.peer.service)'
                            )
                        else:
                            structural_tql = (
                                "{ } >> { } | rate() by (resource.service.name, span.peer.service)"
                            )

                        edge_result = await tempo_service.metrics_query_range(
                            backend_id=backend_id,
                            q=structural_tql,
                            tenant=tenant,
                            start=resolved_start,
                            end=resolved_end,
                        )
                        traceql_metrics_ok = True

                        edge_data = edge_result.get("data", edge_result)
                        for series in edge_data.get("result", []):
                            labels = series.get("metric", {})
                            client_svc = labels.get("resource.service.name", "")
                            server_svc = (
                                labels.get("span.peer.service")
                                or labels.get("span.peer.service.name")
                                or labels.get("span.server.address", "")
                            )
                            if client_svc:
                                nodes_set.add(client_svc)
                            if server_svc:
                                nodes_set.add(server_svc)
                            if client_svc and server_svc and client_svc != server_svc:
                                vals = [
                                    float(v[1])
                                    for v in series.get("values", [])
                                    if len(v) >= 2
                                ]
                                avg_rate = round(sum(vals) / len(vals), 4) if vals else None
                                edges.append({
                                    "client": client_svc,
                                    "server": server_svc,
                                    "call_rate": avg_rate,
                                    "request_rate": avg_rate,
                                    "source": "traceql_metrics",
                                })

                        if edges:
                            method = "traceql_structural"
                            source_used = "traceql_metrics_plus_trace_dag"
                    except Exception:
                        pass

                # Attempt 2: Trace-sampled DAG parent->child service edge extraction (captures upstream + downstream)
                if source_used != "prometheus" and (not edges or service) and sample_traces > 0:
                    try:
                        search_q = (
                            f'{{ resource.service.name = "{service}" }}'
                            if service
                            else "{ duration > 0ns }"
                        )
                        search_res = await tempo_service.traceql_search(
                            backend_id=backend_id,
                            tenant=tenant,
                            q=search_q,
                            start=resolved_start,
                            end=resolved_end,
                            limit=sample_traces,
                        )
                        raw_traces: List[Dict[str, Any]] = []
                        for item in search_res.get("traces", [])[:sample_traces]:
                            tid = item.get("traceID")
                            if item.get("rootServiceName"):
                                nodes_set.add(item["rootServiceName"])
                            if tid:
                                try:
                                    t_resp = await tempo_service.get_trace(
                                        backend_id=backend_id,
                                        trace_id=tid,
                                        tenant=tenant,
                                        llm_format=False,
                                        max_spans=200,
                                    )
                                    if t_resp.get("trace"):
                                        raw_traces.append(t_resp["trace"])
                                except Exception:
                                    continue

                        if raw_traces:
                            dag_nodes, dag_edges = extract_dag_service_edges_from_traces(
                                raw_traces, focus_service=service
                            )
                            nodes_set.update(dag_nodes)
                            existing_pairs = {(e["client"], e["server"]) for e in edges}
                            added_any = False
                            for de in dag_edges:
                                if (de["client"], de["server"]) not in existing_pairs:
                                    edges.append(de)
                                    existing_pairs.add((de["client"], de["server"]))
                                    added_any = True
                            if added_any and method == "service_enumeration":
                                method = "trace_dag_sample"
                            if edges:
                                source_used = (
                                    "traceql_metrics_plus_trace_dag"
                                    if traceql_metrics_ok
                                    else "traceql_search"
                                )
                    except Exception:
                        pass

                # Attempt 3: Service name enumeration via rate()
                if source_used != "prometheus":
                    try:
                        enum_tql = "{ } | rate() by (resource.service.name)"
                        if service:
                            enum_tql = f'{{ resource.service.name = "{service}" }} | rate() by (resource.service.name)'

                        enum_result = await tempo_service.metrics_query_range(
                            backend_id=backend_id,
                            q=enum_tql,
                            tenant=tenant,
                            start=resolved_start,
                            end=resolved_end,
                        )
                        traceql_metrics_ok = True

                        enum_data = enum_result.get("data", enum_result)
                        for series in enum_data.get("result", []):
                            labels = series.get("metric", {})
                            svc = labels.get("resource.service.name") or labels.get("service_name", "")
                            if svc:
                                nodes_set.add(svc)
                        if edges and source_used == "traceql_search":
                            source_used = "traceql_metrics_plus_trace_dag"
                    except Exception:
                        pass

                # Attempt 4: Attribute value fallback
                if not nodes_set:
                    try:
                        attr_result = await tempo_service.get_attribute_values(
                            backend_id=backend_id,
                            attribute="resource.service.name",
                            tenant=tenant,
                            start=resolved_start,
                            end=resolved_end,
                        )
                        for tag_val in attr_result.get("tagValues", []):
                            svc = tag_val.get("value", tag_val) if isinstance(tag_val, dict) else str(tag_val)
                            if svc:
                                nodes_set.add(svc)
                    except Exception:
                        pass

                nodes = [{"service": s} for s in sorted(nodes_set)]
                summary = f"{len(nodes)} services, {len(edges)} edges"
                if service:
                    summary += f" (focus: '{service}')"

                payload: Dict[str, Any] = {
                    "nodes": nodes,
                    "edges": edges,
                    "source_used": source_used,
                    "method": method,
                    "summary": summary,
                }
                if not edges:
                    payload["edges_note"] = (
                        "No cross-service edges observed in Tempo for this window."
                    )
                return payload
            except Exception as e:
                self.handle_error(e, "tempo_get_service_dependencies", backend_id=backend_id)
                raise
