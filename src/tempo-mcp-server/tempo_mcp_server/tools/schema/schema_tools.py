"""Tempo schema discovery tools.

Provides tools for discovering attribute names, values,
and K8s-to-Tempo attribute mappings.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions import TempoOperationError
from tempo_mcp_server.models.schema import VALID_SCOPES
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.traceql_helpers import DEFAULT_K8S_MAP
from tempo_mcp_server.utils.time_helpers import resolve_time_params


class SchemaTools(BaseTool):
    """Attribute / tag schema discovery tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        tempo_service = self.tempo_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Attribute Names",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_attribute_names(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            scope: Optional[str] = Field(
                default="all",
                description=(
                    "Attribute scope filter. Values: all, resource, span, intrinsic, "
                    "event, link, instrumentation."
                ),
            ),
            since: Optional[str] = Field(
                default=None,
                description="Relative time window, e.g. '1h', '6h'. Narrows tag search to recent data.",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Discover available trace attribute names from a Tempo backend.

            Returns attribute names grouped by scope. Use before constructing
            TraceQL queries to understand what attributes exist. Read-only.

            Returns:
            - {"scopes": [{"scope_name": [{"name": str, "scope": str}, ...]}], "total": int}

            When NOT to use: For attribute VALUES (what values an attribute takes),
            use tempo_get_attribute_values instead.

            Common errors:
            - Empty results: Try broadening the time range or scope filter.
            """
            if scope and scope not in VALID_SCOPES:
                raise TempoOperationError(
                    f"Invalid scope: '{scope}'. Valid: {', '.join(VALID_SCOPES)}"
                )

            start, end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info(
                        f"Fetching attribute names from '{backend_id}' "
                        f"(scope={scope or 'all'})..."
                    )
                result = await tempo_service.get_attribute_names(
                    backend_id=backend_id,
                    tenant=tenant,
                    scope=scope if scope != "all" else None,
                    start=start,
                    end=end,
                )

                # Normalize response
                scopes_data = result.get("scopes", [])
                total = sum(len(s.get("tags", [])) for s in scopes_data)

                return {
                    "scopes": scopes_data,
                    "total": total,
                }
            except Exception as e:
                raise TempoOperationError(f"Failed to get attribute names: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Attribute Values",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_attribute_values(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            attribute: str = Field(
                ..., min_length=1,
                description="Attribute name to get values for (e.g. 'service.name', 'http.method')",
            ),
            since: Optional[str] = Field(
                default=None,
                description="Relative time window, e.g. '1h', '24h'",
            ),
            query: Optional[str] = Field(
                default=None,
                description="Optional TraceQL filter to scope values, e.g. '{ status = error }'",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get distinct values for a specific trace attribute.

            Returns the set of values an attribute takes across stored traces.
            Useful for building UI dropdowns or understanding data distribution. Read-only.

            Returns:
            - {"attribute_name": str, "tag_values": [str, ...], "total": int}

            When NOT to use: For listing available attributes, use
            tempo_get_attribute_names first.

            Common errors:
            - Empty values: The attribute may not exist or the time range is too narrow.
            - Truncated results: Tempo enforces max_bytes_per_tag_values_query. Narrow your time range.
            """
            start, end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info(
                        f"Fetching values for attribute '{attribute}'..."
                    )
                result = await tempo_service.get_attribute_values(
                    backend_id=backend_id,
                    attribute=attribute,
                    tenant=tenant,
                    q=query,
                    start=start,
                    end=end,
                )

                tag_values = result.get("tagValues", [])
                values = [tv.get("value", tv) if isinstance(tv, dict) else tv for tv in tag_values]

                return {
                    "attribute_name": attribute,
                    "tag_values": values,
                    "total": len(values),
                    # L-03: `truncated` was a hardcoded heuristic (>= 500) that
                    # gave false confidence. Tempo's actual limit is set server-side
                    # via max_bytes_per_tag_values_query and can be lower or higher.
                    # `possibly_truncated` communicates the uncertainty correctly.
                    "possibly_truncated": len(values) >= 500,
                    "truncation_note": (
                        "Tempo enforces a server-side byte limit on tag value queries "
                        "(max_bytes_per_tag_values_query). If the result looks incomplete, "
                        "narrow the time range with the 'since' parameter."
                    ),
                }
            except Exception as e:
                raise TempoOperationError(f"Failed to get attribute values: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get K8s Attribute Map",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_k8s_attribute_map(
            backend_id: Optional[str] = Field(
                default=None,
                description="Optional backend ID. If provided, validates mappings against live tags.",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID for multi-tenant backends"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get canonical K8s-to-Tempo attribute mapping.

            Returns the mapping between Kubernetes concepts (namespace, pod,
            deployment, etc.) and their OTel/Tempo attribute names. Optionally
            validates against a live backend's tag list. Read-only.

            Returns:
            - {"mappings": [{"semantic_key": str, "preferred_attribute": str, ...}], ...}

            When NOT to use: For raw attribute discovery, use
            tempo_get_attribute_names instead.

            Common errors:
            - None expected; returns static mapping by default.
            """
            mappings = []
            all_k8s_mappings = {
                "namespace": {"candidates": ["k8s.namespace.name", "namespace"], "preferred": "k8s.namespace.name"},
                "pod": {"candidates": ["k8s.pod.name", "pod"], "preferred": "k8s.pod.name"},
                "deployment": {"candidates": ["k8s.deployment.name", "deployment"], "preferred": "k8s.deployment.name"},
                "node": {"candidates": ["k8s.node.name", "node"], "preferred": "k8s.node.name"},
                "cluster": {"candidates": ["k8s.cluster.name", "cluster"], "preferred": "k8s.cluster.name"},
                "container": {"candidates": ["k8s.container.name", "container.name"], "preferred": "k8s.container.name"},
                "service": {"candidates": ["service.name", "k8s.pod.labels.app"], "preferred": "service.name"},
                "environment": {"candidates": ["deployment.environment", "env", "environment"], "preferred": "deployment.environment"},
            }

            for key, info in all_k8s_mappings.items():
                mappings.append({
                    "semantic_key": key,
                    "candidate_attributes": info["candidates"],
                    "preferred_attribute": info["preferred"],
                })

            result: Dict[str, Any] = {"mappings": mappings}

            # Optionally validate against live backend
            if backend_id:
                try:
                    tags_data = await tempo_service.get_attribute_names(
                        backend_id=backend_id, tenant=tenant, scope="resource",
                    )
                    live_tags = set()
                    for scope_data in tags_data.get("scopes", []):
                        for tag in scope_data.get("tags", []):
                            tag_name = tag.get("name", tag) if isinstance(tag, dict) else tag
                            live_tags.add(tag_name)

                    for mapping in mappings:
                        found = [a for a in mapping["candidate_attributes"] if a in live_tags]
                        mapping["live_matches"] = found
                        if found:
                            mapping["preferred_attribute"] = found[0]

                    result["backend_id"] = backend_id
                    result["validated"] = True
                except Exception:
                    result["validated"] = False

            return result
