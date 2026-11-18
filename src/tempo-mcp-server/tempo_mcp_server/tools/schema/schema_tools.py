"""Tempo schema discovery tools."""

from typing import Any, Dict, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from tempo_mcp_server.exceptions import TempoOperationError
from tempo_mcp_server.models.schema import VALID_SCOPES
from tempo_mcp_server.tools.base import BaseTool
from tempo_mcp_server.utils.time_helpers import resolve_time_params


class SchemaTools(BaseTool):
    """Attribute / tag schema discovery tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("search", is_write=False):
            return

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
                description="Scope filter: all, resource, span, intrinsic, event, link, instrumentation",
            ),
            query: Optional[str] = Field(
                default=None,
                description="Optional TraceQL selector to scope discovered attributes",
            ),
            since: Optional[str] = Field(
                default=None,
                description="Relative time window, e.g. '1h', '6h'",
            ),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Discover trace attribute names grouped by scope from a Tempo backend.

            Returns: {"scopes": [{"name": str, "tags": [str, ...]}], "total": int}.
            When NOT to use: For distinct values of a known attribute, call tempo_get_attribute_values.
            """
            if scope and scope not in VALID_SCOPES:
                raise TempoOperationError(
                    f"Invalid scope: '{scope}'. Valid: {', '.join(VALID_SCOPES)}"
                )

            start, end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info(
                        f"Fetching attribute names from '{backend_id}' (scope={scope or 'all'})..."
                    )
                result = await tempo_service.get_attribute_names(
                    backend_id=backend_id,
                    tenant=tenant,
                    scope=scope if scope != "all" else None,
                    q=query,
                    start=start,
                    end=end,
                )

                scopes_data = result.get("scopes", [])
                total = sum(len(s.get("tags", [])) for s in scopes_data)

                return {
                    "scopes": scopes_data,
                    "total": total,
                }
            except Exception as e:
                self.handle_error(e, "tempo_get_attribute_names", backend_id=backend_id)
                raise

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
                description="Attribute name (e.g. 'service.name', 'http.response.status_code')",
            ),
            since: Optional[str] = Field(
                default=None,
                description="Relative time window, e.g. '1h', '24h'",
            ),
            query: Optional[str] = Field(
                default=None,
                description="Optional TraceQL filter to scope values, e.g. '{ status = error }'",
            ),
            limit: Optional[int] = Field(default=None, description="Max values to return"),
            tenant: Optional[str] = Field(default=None, description="Tenant ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Retrieve distinct values for a trace attribute on a Tempo backend.

            Returns: {"attribute_name": str, "tag_values": [str, ...], "total": int, "possibly_truncated": bool}.
            When NOT to use: To list available attribute names, call tempo_get_attribute_names.
            """
            start, end = resolve_time_params(since=since)

            try:
                if ctx:
                    await ctx.info(f"Fetching values for attribute '{attribute}'...")
                result = await tempo_service.get_attribute_values(
                    backend_id=backend_id,
                    attribute=attribute,
                    tenant=tenant,
                    q=query,
                    limit=limit,
                    start=start,
                    end=end,
                )

                tag_values = result.get("tagValues", [])
                values = [
                    tv.get("value", tv) if isinstance(tv, dict) else tv
                    for tv in tag_values
                ]

                return {
                    "attribute_name": attribute,
                    "tag_values": values,
                    "total": len(values),
                    "possibly_truncated": len(values) >= 500,
                }
            except Exception as e:
                self.handle_error(e, "tempo_get_attribute_values", backend_id=backend_id)
                raise
