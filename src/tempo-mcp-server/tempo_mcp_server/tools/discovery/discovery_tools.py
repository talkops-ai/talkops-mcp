"""Tempo backend discovery tools.

Provides tools for listing, inspecting, and querying policies of Tempo backends.
"""

from typing import Any, Dict, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions import TempoOperationError
from tempo_mcp_server.tools.base import BaseTool


class DiscoveryTools(BaseTool):
    """Backend discovery and inspection tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        tempo_service = self.tempo_service
        config = self.config

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Tempo Backends",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_list_backends(
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List all configured Tempo backends with health status.

            Use this first to discover available backends and their current
            health before running any trace queries. Read-only.

            Returns:
            - {"backends": [{"id": str, "type": str, "health": "ready"|"not_ready", ...}], "total": int, "healthy": int}

            When NOT to use: For detailed backend capabilities, use
            tempo_get_backend instead.

            Common errors:
            - All backends unreachable: Verify TEMPO_BASE_URL or TEMPO_BACKENDS configuration.
            """
            try:
                if ctx:
                    await ctx.info("Listing all configured Tempo backends...")
                backends = await tempo_service.list_backends()
                healthy = sum(1 for b in backends if b["health"] == "ready")
                if ctx:
                    await ctx.info(
                        f"Found {len(backends)} backends ({healthy} healthy, "
                        f"{len(backends) - healthy} unhealthy)"
                    )
                return {
                    "backends": backends,
                    "total": len(backends),
                    "healthy": healthy,
                    "unhealthy": len(backends) - healthy,
                }
            except Exception as e:
                raise TempoOperationError(f"Failed to list backends: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Tempo Backend Details",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_backend(
            backend_id: str = Field(
                ..., min_length=1,
                description="Tempo backend ID (from tempo_list_backends)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get detailed profile for a specific Tempo backend.

            Returns health, version, build info, capabilities, deployment mode,
            tenant requirements, and service component statuses. Read-only.

            Returns:
            - {"id": str, "version": str, "capabilities": [...], "services": {...}, ...}

            When NOT to use: For a quick list of all backends, use
            tempo_list_backends instead.

            Common errors:
            - Unknown backend_id: Run tempo_list_backends first to discover valid IDs.
            """
            try:
                if ctx:
                    await ctx.info(f"Fetching details for backend '{backend_id}'...")
                return await tempo_service.get_backend_capabilities(backend_id)
            except Exception as e:
                raise TempoOperationError(f"Failed to get backend details: {e}")

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Query Policies",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
            output_schema=None,
        )
        async def tempo_get_query_policies(
            backend_id: Optional[str] = Field(
                default=None,
                description="Tempo backend ID. If omitted, returns default policy.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get query guardrails and default search parameters.

            Returns max lookback, search limits, spss limits, and time range
            requirements. Use this to understand constraints before constructing
            complex queries. Read-only.

            Returns:
            - {"policies": {"max_lookback": str, "default_search_limit": int, ...}}

            When NOT to use: For backend health and version info, use
            tempo_get_backend instead.

            Common errors:
            - None expected; uses local configuration only.
            """
            policy = config.query_policy
            return {
                "backend_id": backend_id or tempo_service.get_default_backend_id(),
                "policies": {
                    "max_lookback": policy.max_lookback,
                    "default_search_limit": policy.default_search_limit,
                    "max_search_limit": policy.max_search_limit,
                    "default_spss": policy.default_spss,
                    "max_spss": policy.max_spss,
                    "require_time_range": policy.require_time_range,
                    "require_filter_or_query": policy.require_filter_or_query,
                    "default_metrics_sampling": policy.default_metrics_sampling,
                },
            }
