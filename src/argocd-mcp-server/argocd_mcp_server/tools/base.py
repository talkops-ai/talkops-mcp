"""Base class for all ArgoCD MCP tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Literal, Optional
from fastmcp import Context
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)

from argocd_mcp_server.config import ServerConfig


class BaseTool(ABC):
    """Abstract base class for all tool groups."""

    toolset_name: str = "applications"

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator."""
        self.service_locator = service_locator
        self.argocd_service: Any = service_locator.get("argocd_service")
        self.mgmt_service: Any = service_locator.get("mgmt_service")
        self.config: Optional[ServerConfig] = service_locator.get("config")

    def should_register_tool(
        self,
        *,
        is_read_only: bool,
        supports_dry_run: bool = False,
    ) -> bool:
        """Return True if a tool should be registered under current write/toolset settings."""
        if self.config and not self.config.allow_write:
            return is_read_only or supports_dry_run
        return True

    async def confirm_destructive_action(
        self,
        ctx: Optional[Context],
        action_description: str,
        confirm: bool = False,
        impact_preview: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Gate high-blast-radius operations behind MCP Elicitation or two-step confirm=True fallback.

        Returns:
            None when confirmed (proceed with execution), or a structured response dict
            when declined/cancelled or awaiting confirmation.
        """
        if confirm:
            return None

        if ctx is not None and hasattr(ctx, "elicit"):
            try:
                elicitation = await ctx.elicit(
                    f"Confirm destructive ArgoCD operation: {action_description}",
                    response_type=["confirm", "abort"],
                )
                if (
                    isinstance(elicitation, AcceptedElicitation)
                    and getattr(elicitation, "data", None) == "confirm"
                ):
                    return None
                if isinstance(
                    elicitation,
                    (AcceptedElicitation, DeclinedElicitation, CancelledElicitation),
                ):
                    return {
                        "status": "aborted",
                        "confirmed": False,
                        "message": (
                            f"Operation aborted by operator: {action_description}. "
                            "No changes were made."
                        ),
                    }
            except Exception:
                # Client host does not implement elicitation callback; use two-step confirm=True fallback
                pass

        return {
            "status": "confirmation_required",
            "requires_confirmation": True,
            "confirmed": False,
            "impact_preview": impact_preview or {"operation": action_description},
            "message": (
                f"Confirmation required for destructive operation: {action_description}. "
                "Present the impact preview to the operator and re-call with confirm=True to execute."
            ),
        }

    @staticmethod
    async def _log_info(ctx: Optional[Context], msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if ctx is not None and hasattr(ctx, "info"):
            await ctx.info(msg, extra=extra)

    @staticmethod
    async def _log_warning(ctx: Optional[Context], msg: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if ctx is not None and hasattr(ctx, "warning"):
            await ctx.warning(msg, extra=extra)

    @staticmethod
    async def _log_error(ctx: Optional[Context], msg: str) -> None:
        if ctx is not None and hasattr(ctx, "error"):
            await ctx.error(msg)

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register tools with FastMCP instance."""
        pass
