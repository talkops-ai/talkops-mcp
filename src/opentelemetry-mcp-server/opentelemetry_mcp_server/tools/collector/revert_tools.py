"""Collector config revert tool.

Provides the ``otel_revert_collector_config`` tool for undoing the last
MCP-driven configuration change. Uses the annotation-based config
snapshot stored automatically by ``create_or_patch_collector``.
"""

from typing import Any, Dict

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import BaseTool


class RevertTools(BaseTool):
    """Collector config rollback tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        kubernetes_service = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Revert Collector Config",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_revert_collector_config(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            collector_name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, shows diff between current and snapshot. "
                    "Set False to apply the rollback."
                ),
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Revert a collector to its pre-mutation config (one-level undo).

            Use this when an MCP tool mutation broke the pipeline (e.g.,
            otel_toggle_sampling_strategy or otel_enable_spanmetrics_for_service
            caused issues). Restores from the auto-saved config snapshot.

            **WARNING: This is a one-level undo — it reverts to the config
            from before the LAST MCP mutation. For multi-step rollback,
            use GitOps (git revert + ArgoCD/Flux).**

            Returns:
            - {"action": "reverted"|"dry_run"|"no_snapshot", "snapshot_timestamp": str,
               "current_config_preview": str, "snapshot_config_preview": str, ...}

            When NOT to use: For inspecting configs without reverting, use
            otel_get_collector. For provisioning new collectors, use
            otel_provision_collector.

            Prerequisites: The collector must have been previously modified
            by an MCP tool (which auto-creates the snapshot annotation).

            Common errors:
            - No snapshot found: Collector was not modified by MCP tools.
            - Snapshot corrupted: Manual annotation edits may break decoding.
            """
            try:
                result = await kubernetes_service.revert_collector_config(
                    namespace=namespace,
                    name=collector_name,
                    dry_run=dry_run,
                )
                return result
            except OtelOperationError:
                raise
            except Exception as e:
                raise OtelOperationError(
                    f"Failed to revert collector config: {e}"
                )
