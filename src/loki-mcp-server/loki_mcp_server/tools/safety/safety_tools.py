"""Safety and cost estimation tools — query preflight.

v4 Tool: get_query_stats
"""

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.logql_helpers import validate_stream_selector
from loki_mcp_server.utils.time_utils import parse_relative_time


def _humanize_bytes(byte_count: int) -> str:
    """Convert raw byte count to human-readable string."""
    if byte_count > 1e9:
        return f"{byte_count / 1e9:.2f} GB"
    elif byte_count > 1e6:
        return f"{byte_count / 1e6:.2f} MB"
    elif byte_count > 1e3:
        return f"{byte_count / 1e3:.2f} KB"
    return f"{byte_count} B"


class SafetyTools(BaseTool):
    """Query cost estimation and preflight tools.

    These tools must be called before heavy queries to
    prevent backend overload.
    """

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all safety tools with the MCP instance."""
        loki = self.loki_service
        config = self.config

        # ──────────────────────────────────────────
        # Tool 6: get_query_stats
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Query Stats",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def get_query_stats(
            query: str = Field(
                ...,
                min_length=1,
                description=(
                    "LogQL stream selector. CRITICAL: MUST be wrapped in curly "
                    "braces {label=\"value\"}. "
                    "CORRECT: '{app=\"checkout\"}'. "
                    "WRONG: 'app=\"checkout\"' (missing braces). "
                    "WRONG: '{{app=\"checkout\"}}' (double braces)."
                ),
            ),
            start: Optional[str] = Field(
                default=None,
                description="Start timestamp (RFC3339 or relative)",
            ),
            end: Optional[str] = Field(
                default=None,
                description="End timestamp (RFC3339 or relative)",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID) for multi-tenant Loki",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Preflight a selector to estimate query cost.

            **Always check streams/chunks/bytes before heavy queries.**
            Returns the number of streams, chunks, entries, and bytes
            a query would touch. Cancel or narrow queries when bytes
            or streams exceed configurable thresholds. Read-only.

            Returns:
            - {"streams": int, "chunks": int, "entries": int, "bytes": int,
               "human_bytes": str, "exceeds_threshold": bool,
               "threshold_bytes": int}

            When NOT to use: For executing queries use execute_logql_query
            or execute_logql_instant.

            Common errors:
            - Stats not available: Some Loki deployments disable this endpoint.
            """
            if ctx:
                await ctx.info(f"Estimating query cost for '{query}'...")

            query = validate_stream_selector(query)

            s = parse_relative_time(start) if start else None
            e = parse_relative_time(end) if end else None

            stats = await loki.get_index_stats(query=query, start=s, end=e, org_id=org_id)

            query_bytes = stats.get("bytes", 0)
            exceeds = query_bytes > config.guardrails.max_query_bytes

            if ctx:
                human = _humanize_bytes(query_bytes)
                await ctx.info(
                    f"Query would touch {human}"
                    f"{' ⚠️ EXCEEDS THRESHOLD' if exceeds else ''}"
                )

            return {
                "streams": stats.get("streams", 0),
                "chunks": stats.get("chunks", 0),
                "entries": stats.get("entries", 0),
                "bytes": query_bytes,
                "human_bytes": _humanize_bytes(query_bytes),
                "exceeds_threshold": exceeds,
                "threshold_bytes": config.guardrails.max_query_bytes,
            }
