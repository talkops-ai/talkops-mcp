"""Discovery tools — indexed label names, label values, and active stream series.

Tools (`discovery` toolset, read-only):
- loki_get_labels
- loki_get_label_values
- loki_get_series
"""

from typing import Any, Dict, List, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.time_utils import parse_relative_time


class DiscoveryTools(BaseTool):
    """Label taxonomy and active series discovery tools (`discovery` toolset)."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all discovery tools with the MCP instance."""
        loki = self.loki_service
        config = self.config
        if not config.should_register("discovery", is_write=False):
            return

        # ──────────────────────────────────────────
        # Tool 1: loki_get_labels
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Loki Indexed Labels",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_get_labels(
            start: Optional[str] = Field(
                default=None,
                description="Start timestamp (RFC3339 or relative like 'now-24h')",
            ),
            end: Optional[str] = Field(
                default=None,
                description="End timestamp (RFC3339 or relative like 'now')",
            ),
            org_id: Optional[str] = Field(
                default=None,
                description="Optional tenant ID (X-Scope-OrgID) for multi-tenant Loki",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List all indexed label names in Grafana Loki over an optional time window. Read-only."""
            if ctx:
                await ctx.info("Discovering label taxonomy...")

            s = parse_relative_time(start) if start else None
            e = parse_relative_time(end) if end else None

            labels = await loki.get_labels(start=s, end=e, org_id=org_id)

            if ctx:
                await ctx.info(f"Found {len(labels)} labels")

            return {
                "labels": labels,
                "count": len(labels),
            }

        # ──────────────────────────────────────────
        # Tool 2: loki_get_label_values
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Loki Label Values",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_get_label_values(
            label: str = Field(
                ...,
                min_length=1,
                description="Indexed label name to retrieve values for (from loki_get_labels)",
            ),
            query: Optional[str] = Field(
                default=None,
                description="Optional LogQL stream selector to scope values (e.g., '{namespace=\"prod\"}')",
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
            """Retrieve values for a specific indexed label in Grafana Loki, optionally scoped by stream selector. Read-only."""
            if ctx:
                await ctx.info(f"Fetching values for label '{label}'...")

            s = parse_relative_time(start) if start else None
            e = parse_relative_time(end) if end else None

            values = await loki.get_label_values(
                label=label, query=query, start=s, end=e, org_id=org_id
            )

            if ctx:
                await ctx.info(f"Found {len(values)} values for '{label}'")

            return {
                "label": label,
                "values": values,
                "count": len(values),
            }

        # ──────────────────────────────────────────
        # Tool 3: loki_get_series
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Active Loki Log Streams",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def loki_get_series(
            match: str = Field(
                ...,
                min_length=1,
                description="LogQL stream selector (MUST start with '{', e.g., '{app=\"checkout\"}')",
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
            """Return active Loki log stream label sets and per-label cardinality for a stream selector. Read-only."""
            if ctx:
                await ctx.info(f"Validating selector '{match}'...")

            s = parse_relative_time(start) if start else None
            e = parse_relative_time(end) if end else None

            series = await loki.get_series(match=match, start=s, end=e, org_id=org_id)

            if ctx:
                await ctx.info(f"Found {len(series)} active series")

            label_values: Dict[str, set] = {}
            for s_item in series:
                for k, v in s_item.items():
                    if k not in label_values:
                        label_values[k] = set()
                    label_values[k].add(v)

            threshold = config.guardrails.high_cardinality_threshold
            label_cardinality: Dict[str, int] = {
                name: len(vals) for name, vals in sorted(label_values.items())
            }

            warnings: List[str] = []
            for label_name, unique_count in label_cardinality.items():
                if unique_count > threshold:
                    warnings.append(
                        f"Label '{label_name}' has {unique_count} unique values "
                        f"(threshold: {threshold})."
                    )

            return {
                "matcher": match,
                "total_series": len(series),
                "series": series,
                "label_cardinality": label_cardinality,
                "warnings": warnings,
            }
