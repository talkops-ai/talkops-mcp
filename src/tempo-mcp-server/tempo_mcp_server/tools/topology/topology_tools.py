"""Tempo service topology / dependencies tool.

Derives service dependencies from TraceQL structural queries (Tempo 2.4+)
using the `>>` child-span operator to find actual client→server call edges.
Falls back to service-name enumeration when metrics-generator is unavailable.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions import TempoOperationError
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.time_helpers import resolve_time_params


class TopologyTools(BaseTool):
    """Service topology and dependency mapping tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

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
                description="Focus on a specific service's dependencies",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Map service dependencies from Tempo trace topology.

            Uses TraceQL structural queries (>>) to derive actual client→server
            edges from trace data (requires Tempo 2.4+). Falls back to
            service-name enumeration when structural queries are unavailable.

            Returns:
            - {"nodes": [{"service": str}], "edges": [{"client": str,
               "server": str}], "method": "traceql_structural"|"service_enumeration",
               "edges_note": str|null}

            When NOT to use: For service-specific trace search, use
            tempo_traceql_search with the service filter.

            Common errors:
            - Empty results: No traces in the time window. Extend `since`.
            - No edges: Tempo 2.4+ required for structural queries, or
              metrics-generator service_graphs must be enabled.
              Use tempo_get_diagnostics to verify.
            """
            resolved_start, resolved_end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info(
                        f"Mapping service dependencies from '{backend_id}'..."
                    )
                nodes_set: set = set()
                edges: List[Dict[str, Any]] = []
                method = "service_enumeration"
                edges_note: Optional[str] = None

                # ── Attempt 1: TraceQL structural edge derivation (Tempo 2.4+) ──
                # `{ } >> { }` matches any parent span followed by a child span
                # across potentially different services — gives us call edges.
                try:
                    if service:
                        # Edges where the focused service is caller or callee
                        structural_tql = (
                            f'{{ resource.service.name = "{service}" }} >> {{ }}'
                            f' | by(resource.service.name, span.peer.service.name)'
                        )
                    else:
                        structural_tql = (
                            "{ } >> { }"
                            " | by(resource.service.name, span.peer.service.name)"
                        )

                    edge_result = await tempo_service.metrics_query_range(
                        backend_id=backend_id,
                        q=structural_tql,
                        tenant=tenant,
                        start=resolved_start,
                        end=resolved_end,
                    )

                    edge_data = edge_result.get("data", edge_result)
                    for series in edge_data.get("result", []):
                        labels = series.get("metric", {})
                        client_svc = labels.get("resource.service.name", "")
                        server_svc = labels.get("span.peer.service.name", "")
                        if client_svc:
                            nodes_set.add(client_svc)
                        if server_svc:
                            nodes_set.add(server_svc)
                        if client_svc and server_svc and client_svc != server_svc:
                            edges.append({
                                "client": client_svc,
                                "server": server_svc,
                            })

                    if edges:
                        method = "traceql_structural"

                except Exception:
                    # Structural queries not supported — fall through to
                    # service enumeration below.
                    pass

                # ── Attempt 2: Service name enumeration via rate() ──
                # (always run to populate nodes even if edges succeeded)
                try:
                    enum_tql = "{ } | by(resource.service.name) | rate()"
                    if service:
                        enum_tql = (
                            f'{{ resource.service.name = "{service}" }}'
                            " | by(resource.service.name) | rate()"
                        )

                    enum_result = await tempo_service.metrics_query_range(
                        backend_id=backend_id,
                        q=enum_tql,
                        tenant=tenant,
                        start=resolved_start,
                        end=resolved_end,
                    )

                    enum_data = enum_result.get("data", enum_result)
                    for series in enum_data.get("result", []):
                        labels = series.get("metric", {})
                        svc = labels.get("resource.service.name") or labels.get("service_name", "")
                        if svc:
                            nodes_set.add(svc)

                except Exception:
                    pass

                # ── Attempt 3: Attribute value fallback (no metrics-generator) ──
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
                            svc = tag_val.get("value", "")
                            if svc:
                                nodes_set.add(svc)
                        method = "service_enumeration"
                    except Exception:
                        pass

                if method == "service_enumeration" and not edges:
                    edges_note = (
                        "Edge data unavailable: TraceQL structural queries (>>) require "
                        "Tempo 2.4+ with metrics-generator enabled. "
                        "Nodes are enumerated from known service names only."
                    )

                nodes = [{"service": s} for s in sorted(nodes_set)]
                summary = f"{len(nodes)} services found"
                if service:
                    summary += f" related to '{service}'"

                return {
                    "nodes": nodes,
                    "edges": edges,
                    "method": method,
                    "summary": summary,
                    **({"edges_note": edges_note} if edges_note else {}),
                }
            except Exception as e:
                raise TempoOperationError(f"Failed to get service dependencies: {e}")

