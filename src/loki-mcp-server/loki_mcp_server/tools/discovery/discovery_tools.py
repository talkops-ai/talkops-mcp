"""Discovery tools — label taxonomy, label values, and active series validation.

v4 Tools: get_cluster_labels, get_label_values, get_active_series
"""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from loki_mcp_server.tools.base import BaseTool
from loki_mcp_server.utils.error_handling import tool_error_boundary
from loki_mcp_server.utils.time_utils import parse_relative_time


class DiscoveryTools(BaseTool):
    """Label taxonomy and active series validation tools.

    These tools must be called BEFORE any query execution
    to discover available dimensions and validate selectors.
    """

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all discovery tools with the MCP instance."""
        loki = self.loki_service
        config = self.config

        # ──────────────────────────────────────────
        # Tool 1: get_cluster_labels
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Cluster Labels",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def get_cluster_labels(
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
            """Discover global label taxonomy in Loki.

            **Always call first** before writing any LogQL queries.
            Returns the exact label names available so you don't
            hallucinate labels that don't exist. Read-only.

            Returns:
            - {"labels": [str], "count": int}

            When NOT to use: For label VALUES use get_label_values.
            For validating selectors use get_active_series.

            Common errors:
            - Empty list: No data ingested in the time range. Widen the window.
            - Connection error: Loki is unreachable. Check LOKI_URL config.
            """
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
        # Tool 2: get_label_values
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Label Values",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def get_label_values(
            label: str = Field(
                ...,
                min_length=1,
                description="Label name to get values for (from get_cluster_labels output)",
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
            """Discover concrete values for a label.

            **Use to learn naming** — call after get_cluster_labels to
            discover valid label values (namespaces, apps, clusters)
            before writing LogQL queries. Read-only.

            Returns:
            - {"label": str, "values": [str], "count": int}

            When NOT to use: For listing label NAMES use get_cluster_labels.
            For validating full selectors use get_active_series.

            Common errors:
            - Empty values: Label exists but has no data in the time range.
            - Unknown label: Use get_cluster_labels first to see available labels.
            """
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
        # Tool 3: get_active_series
        # ──────────────────────────────────────────
        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Active Series",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        @tool_error_boundary
        async def get_active_series(
            match: str = Field(
                ...,
                min_length=1,
                description="LogQL stream selector (MUST start with '{', e.g., '{app=\"checkout\"}'). Do NOT pass PromQL queries or metric queries like 'rate(...)'.",
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
            """Validate that selectors correspond to active streams.

            **Confirm selectors before queries** — call this to verify
            that a stream selector matches real data before running
            expensive execute_logql_query calls. Also returns per-label
            cardinality to help identify high-cardinality labels that
            should NOT be placed in {} stream selectors. Read-only.

            Returns:
            - {"matcher": str, "total_series": int,
               "series": [{"label_key": "value", ...}],
               "label_cardinality": {"label_name": int},
               "warnings": [str]}

            When NOT to use: For listing label names use get_cluster_labels.
            For querying logs use execute_logql_query.

            Common errors:
            - Too many series: Narrow the time range or add more selectors.
            - Empty result: No matching series — check label names/values.
            """
            if ctx:
                await ctx.info(f"Validating selector '{match}'...")

            s = parse_relative_time(start) if start else None
            e = parse_relative_time(end) if end else None

            series = await loki.get_series(match=match, start=s, end=e, org_id=org_id)

            if ctx:
                await ctx.info(f"Found {len(series)} active series")

            # Compute per-label cardinality for enrichment
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
                        f"(threshold: {threshold}). Do NOT use in {{}} stream "
                        f"selectors — use structured metadata or line filters."
                    )

            return {
                "matcher": match,
                "total_series": len(series),
                "series": series,
                "label_cardinality": label_cardinality,
                "warnings": warnings,
            }
