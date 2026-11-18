"""Collector config revert tool.

Provides ``otel_revert_collector_config`` for undoing the last MCP-driven
configuration mutation using the ``otel.mcp/last-known-good`` annotation.
"""

from typing import Any, Dict

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from opentelemetry_mcp_server.exceptions import OtelOperationError
from opentelemetry_mcp_server.tools.base import (
    BaseTool,
    confirm_destructive_action,
)
from opentelemetry_mcp_server.utils.redaction import redact_log_text


class RevertTools(BaseTool):
    """Collector config rollback tools."""

    def register(self, mcp_instance: Any) -> None:
        if not self.should_register_tool("collector", is_write=True):
            return

        kubernetes_service = self.kubernetes_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Revert Collector Config",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def otel_revert_collector_config(
            namespace: str = Field(
                ..., min_length=1, description="Collector namespace"
            ),
            name: str = Field(
                ..., min_length=1, description="Collector CRD name"
            ),
            dry_run: bool = Field(
                default=True,
                description=(
                    "If True, previews the snapshot rollback without applying. "
                    "Set False with confirm=True to apply the rollback."
                ),
            ),
            confirm: bool = Field(
                default=False,
                description="Set True to confirm applying the rollback when dry_run=False",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Revert a collector to its pre-mutation config snapshot (one-level undo).

            Restores the configuration stored in ``otel.mcp/last-known-good``
            before the most recent MCP mutation. Requires confirmation when
            dry_run=False.
            """
            try:
                if not dry_run:
                    self.require_write_access("otel_revert_collector_config")
                    confirmed = await confirm_destructive_action(
                        ctx,
                        f"Revert collector '{namespace}/{name}' to last-known-good snapshot",
                        confirm=confirm,
                    )
                    if not confirmed:
                        return {
                            "collector": f"{namespace}/{name}",
                            "action": "confirmation_required",
                            "dry_run": False,
                            "message": (
                                f"Rollback of collector '{namespace}/{name}' requires "
                                "confirmation. Pass confirm=True to proceed."
                            ),
                        }

                result = await kubernetes_service.revert_collector_config(
                    namespace=namespace,
                    name=name,
                    dry_run=dry_run,
                )
                if "current_config_preview" in result:
                    result["current_config_preview"] = redact_log_text(
                        result["current_config_preview"]
                    )
                if "snapshot_config_preview" in result:
                    result["snapshot_config_preview"] = redact_log_text(
                        result["snapshot_config_preview"]
                    )
                return result
            except OtelOperationError:
                raise
            except Exception as e:
                self.handle_error(
                    e,
                    tool_name="otel_revert_collector_config",
                    namespace=namespace,
                    resource_name=name,
                )
                raise
