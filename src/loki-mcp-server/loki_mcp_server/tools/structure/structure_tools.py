"""Structure and schema tools — log patterns and detected fields.

Tools (`discovery` toolset, read-only):
- loki_get_log_patterns
- loki_get_detected_fields
"""

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.exceptions import LokiResourceNotFoundError
from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.time_utils import parse_relative_time


class StructureTools(BaseTool):
    """Log structure analysis tools (`discovery` toolset)."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all structure tools with the MCP instance."""
        loki = self.loki_service
        if not self.config.should_register("discovery", is_write=False):
            return

        # ──────────────────────────────────────────
        # Tool 4: loki_get_log_patterns
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Loki Log Patterns",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_get_log_patterns(
            query: str = Field(
                ...,
                min_length=1,
                description="LogQL stream selector (e.g., '{app=\"checkout\"}')",
            ),
            start: str = Field(
                default="now-3h",
                description="Start timestamp (RFC3339 or relative)",
            ),
            end: str = Field(
                default="now",
                description="End timestamp (RFC3339 or relative)",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID) for multi-tenant Loki",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Retrieve recurring structural `<_>` log patterns and line counts from Loki's pattern ingester. Read-only."""
            if ctx:
                await ctx.info(f"Discovering log patterns for '{query}'...")

            s = parse_relative_time(start)
            e = parse_relative_time(end)

            try:
                raw_patterns = await loki.get_patterns(
                    query=query, start=s, end=e, org_id=org_id
                )
            except LokiResourceNotFoundError:
                return {
                    "patterns": [],
                    "total_patterns": 0,
                    "suggested_parsers": [],
                    "warning": (
                        "Pattern ingester is not enabled on this Loki instance "
                        "(/loki/api/v1/patterns returned 404)."
                    ),
                }

            patterns: List[Dict[str, Any]] = []
            for p in raw_patterns:
                total_count = 0
                samples = p.get("samples", [])
                for sample in samples:
                    if isinstance(sample, (list, tuple)) and len(sample) >= 2:
                        total_count += int(sample[1])

                patterns.append({
                    "pattern": p.get("pattern", ""),
                    "total_count": total_count,
                })

            patterns.sort(key=lambda x: x["total_count"], reverse=True)

            suggested_parsers: List[str] = []
            for p in patterns[:5]:
                pattern_str = p["pattern"]
                if pattern_str:
                    suggested_parsers.append(f'| pattern "{pattern_str}"')

            return {
                "patterns": patterns,
                "total_patterns": len(patterns),
                "suggested_parsers": suggested_parsers,
            }

        # ──────────────────────────────────────────
        # Tool 5: loki_get_detected_fields
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Loki Detected Fields",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_get_detected_fields(
            query: str = Field(
                ...,
                min_length=1,
                description="LogQL stream selector (e.g., '{app=\"checkout\"}')",
            ),
            start: Optional[str] = Field(
                default=None,
                description="Start timestamp (RFC3339 or relative)",
            ),
            end: Optional[str] = Field(
                default=None,
                description="End timestamp (RFC3339 or relative)",
            ),
            line_limit: Optional[int] = Field(
                default=None,
                description="Max log lines to scan per shard (default: 100)",
            ),
            field_limit: Optional[int] = Field(
                default=None,
                description="Max fields to return (default: 1000)",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID) for multi-tenant Loki",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Discover structured metadata, JSON keys, and logfmt fields with types and cardinalities in Loki 3.x streams. Read-only."""
            if ctx:
                await ctx.info(f"Detecting structured fields for '{query}'...")

            s = parse_relative_time(start) if start else None
            e = parse_relative_time(end) if end else None

            data = await loki.get_detected_fields(
                query=query,
                start=s,
                end=e,
                line_limit=line_limit,
                field_limit=field_limit,
                org_id=org_id,
            )

            fields = data.get("fields", [])

            if ctx:
                await ctx.info(f"Detected {len(fields)} structured fields")

            return {
                "fields": fields,
                "total_fields": len(fields),
            }
