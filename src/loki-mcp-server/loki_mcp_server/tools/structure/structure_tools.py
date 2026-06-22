"""Structure and schema tools — log patterns and detected fields.

v4 Tools: get_log_patterns, get_detected_fields
"""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.exceptions import LokiResourceNotFoundError
from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.time_utils import parse_relative_time


class StructureTools(BaseTool):
    """Log structure analysis tools.

    These tools help understand log shape (patterns, fields, parsers)
    before building LogQL pipelines, reducing trial-and-error and
    context-window waste.
    """

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all structure tools with the MCP instance."""
        loki = self.loki_service

        # ──────────────────────────────────────────
        # Tool 4: get_log_patterns
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Log Patterns",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def get_log_patterns(
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
            """Understand structural patterns of logs without raw text.

            **Use to infer formats and fields** — returns structural
            patterns found in logs, useful for building
            | pattern <field> expressions. Loki's pattern mining is
            ephemeral (typically last 3 hours). Read-only.

            Returns:
            - {"patterns": [{"pattern": str, "total_count": int}],
               "total_patterns": int, "suggested_parsers": [str]}

            When NOT to use: For discovering structured fields
            (JSON/logfmt keys) use get_detected_fields.
            For raw log lines use execute_logql_query.

            Prerequisites: Loki must have pattern_ingester.enabled: true.

            Common errors:
            - 404 error: Pattern ingester not enabled in Loki config.
            - Empty patterns: No patterns detected — try a different stream.
            """
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
                        "Pattern ingester is not enabled on this Loki "
                        "instance. The /loki/api/v1/patterns endpoint "
                        "returned 404. Enable "
                        "pattern_ingester.enabled: true in Loki config "
                        "to use this feature. "
                        "Use get_detected_fields as an alternative."
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

            # Sort by count descending
            patterns.sort(key=lambda x: x["total_count"], reverse=True)

            # Auto-suggest parsers from top patterns
            suggested_parsers: List[str] = []
            for p in patterns[:5]:
                pattern_str = p["pattern"]
                if pattern_str:
                    suggested_parsers.append(
                        f'| pattern "{pattern_str}"'
                    )

            return {
                "patterns": patterns,
                "total_patterns": len(patterns),
                "suggested_parsers": suggested_parsers,
            }

        # ──────────────────────────────────────────
        # Tool 5: get_detected_fields
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Detected Fields",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def get_detected_fields(
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
            """Discover structured keys available in logs.

            **Use to know which fields you can query** — returns
            JSON/logfmt field names, their inferred types, estimated
            cardinality, and the parser needed to extract them.
            Essential for building LogQL pipelines with the correct
            parser (| json, | logfmt) and field names. Read-only.

            Returns:
            - {"fields": [{"label": str, "type": str, "cardinality": int,
                           "parsers": [str]}],
               "total_fields": int}

            When NOT to use: For discovering structural patterns
            use get_log_patterns. For label names use get_cluster_labels.

            Common errors:
            - Empty fields: Logs may be unstructured (plain text).
            - 404 error: Detected fields endpoint requires Loki 3.0+.
            """
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
