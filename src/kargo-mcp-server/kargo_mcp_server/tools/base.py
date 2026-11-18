"""Base class and helper functions for all Kargo MCP Server tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Literal, Optional

from fastmcp import Context
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)

from kargo_mcp_server.config import ServerConfig
from kargo_mcp_server.exceptions.custom import (
    KargoApiError,
    KargoConflictError,
    KargoPermissionError,
    KargoPromotionError,
    KargoResourceNotFoundError,
    KargoValidationError,
    KargoVerificationError,
)


async def confirm_destructive_action(
    ctx: Optional[Context],
    action_summary: str,
    confirm: bool = False,
    resource_uri: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """Gate destructive operations via MCP Elicitation with a confirm=True fallback.

    Returns True when confirmed and execution should proceed, or False when
    declined/cancelled or when confirm=False without interactive elicitation.
    """
    if confirm:
        return True

    if ctx is not None and hasattr(ctx, "elicit"):
        try:
            elicitation = await ctx.elicit(  # type: ignore[call-overload]
                f"Confirm destructive operation: {action_summary}?",
                response_type=Literal["confirm", "abort"],  # type: ignore[arg-type]
            )
            if (
                isinstance(elicitation, AcceptedElicitation)
                and getattr(elicitation, "data", None) == "confirm"
            ):
                return True
            if isinstance(
                elicitation,
                (AcceptedElicitation, DeclinedElicitation, CancelledElicitation),
            ):
                return False
        except Exception:
            # Client host does not implement an elicitation handler; fall back to confirm flag
            pass

    return False


def translate_error(
    exc: Exception,
    tool_name: str,
    project: str = "default",
    resource_name: Optional[str] = None,
) -> ToolError:
    """Translate domain and Kargo REST API exceptions into model-directed ToolError feedback."""
    if type(exc) is ToolError:
        return exc

    target = resource_name or "<name>"
    msg = str(exc)

    if isinstance(exc, KargoApiError):
        body_snippet = f" — {exc.body[:200]}" if exc.body else ""
        if exc.status_code == 404:
            return ToolError(
                f"Resource '{target}' not found in project '{project}' ({exc.message}{body_snippet}). "
                f"Read 'kargo://projects/{project}/pipeline' or 'kargo://projects' to verify valid names."
            )
        if exc.status_code in (401, 403):
            return ToolError(
                f"RBAC permission denied in project '{project}' during {tool_name} ({exc.message}{body_snippet}). "
                f"Read 'kargo://projects/{project}/roles' or 'kargo://server/capabilities' to verify "
                "Kargo ServiceAccount permissions (e.g. 'promote' verb on stages)."
            )
        if exc.status_code == 409:
            return ToolError(
                f"Resource conflict on '{target}' in project '{project}' ({exc.message}{body_snippet}). "
                f"Read 'kargo://projects/{project}/pipeline' and retry."
            )
        if exc.status_code == 422:
            return ToolError(
                f"Kargo schema or admission webhook validation failed on '{target}' in project '{project}' "
                f"({exc.message}{body_snippet}). Call kargo_diagnose_stage(project='{project}', stage='{target}') "
                f"or kargo_diagnose_warehouse(project='{project}', warehouse='{target}') to inspect spec errors."
            )

    if isinstance(exc, KargoResourceNotFoundError):
        return ToolError(
            f"{msg}. Read 'kargo://projects/{project}/pipeline' or 'kargo://projects' "
            f"to verify valid Stage, Warehouse, and Freight names in project '{project}'."
        )
    if isinstance(exc, KargoPermissionError):
        return ToolError(
            f"RBAC permission denied in project '{project}' during {tool_name}: {msg}. "
            f"Read 'kargo://projects/{project}/roles' to inspect role bindings and claims."
        )
    if isinstance(exc, KargoConflictError):
        return ToolError(
            f"Resource conflict in project '{project}': {msg}. "
            f"Read 'kargo://projects/{project}/pipeline' to inspect current state and retry."
        )
    if isinstance(exc, KargoPromotionError):
        return ToolError(
            f"{msg}. Call kargo_diagnose_stage(project='{project}', stage='{target}') "
            f"or kargo_trace_freight(project='{project}', freight_or_alias='<id>') to check "
            "freight availability, upstream verification, soak time, and approval status."
        )
    if isinstance(exc, KargoVerificationError):
        return ToolError(
            f"{msg}. Read 'kargo://projects/{project}/stages/{target}' or "
            f"'kargo://projects/{project}/analysis-templates' and call "
            f"kargo_diagnose_stage(project='{project}', stage='{target}') to inspect verification status."
        )
    if isinstance(exc, (KargoValidationError, ValueError)):
        return ToolError(
            f"Validation error in {tool_name}: {msg}. "
            f"Read 'kargo://projects/{project}/pipeline' to inspect current project topology and configuration."
        )

    return ToolError(
        f"{tool_name} failed: {msg}. Read 'kargo://projects/{project}/pipeline' or call "
        f"kargo_diagnose_stage(project='{project}', stage='{target}') to diagnose pipeline state."
    )


class BaseTool(ABC):
    """Abstract base class for all tools with write gates, elicitation, and error translation."""

    def __init__(self, service_locator: Dict[str, Any]):
        self.kargo_service: Any = service_locator.get("kargo_service")
        self.config: ServerConfig = service_locator.get("config") or ServerConfig()

    def should_register_tool(self, toolset: str, is_write: bool = False) -> bool:
        """Determine whether a tool should be registered given active toolsets and write gate."""
        active_toolsets = self.config.toolsets if self.config else ["all"]
        allow_write = bool(self.config.allow_write) if self.config else False

        if is_write and not allow_write:
            return False

        if "readonly" in active_toolsets and is_write:
            return False

        if "all" in active_toolsets or "readonly" in active_toolsets:
            return True

        return toolset.lower() in active_toolsets

    def should_register(self, toolset: str, is_write: bool = False) -> bool:
        """Alias for should_register_tool."""
        return self.should_register_tool(toolset=toolset, is_write=is_write)

    def require_write_access(self, tool_name: str) -> None:
        """Defense-in-depth write gate enforcement."""
        if not self.config or not self.config.allow_write:
            raise ToolError(
                f"Tool '{tool_name}' is blocked because the server is running in read-only mode "
                "(MCP_ALLOW_WRITE=false). Start the server with --allow-write or set "
                "MCP_ALLOW_WRITE=true to enable Kargo mutations, or use read-only resources "
                "(kargo://projects/{project}/pipeline) and diagnostic tools "
                "(kargo_diagnose_stage, kargo_diagnose_warehouse, kargo_trace_freight, kargo_query_freight)."
            )

    def check_write_access(self, tool_name: str) -> None:
        """Alias for require_write_access."""
        self.require_write_access(tool_name)

    def handle_error(
        self,
        exc: Exception,
        tool_name: str,
        project: str = "default",
        resource_name: Optional[str] = None,
    ) -> None:
        """Translate exception into a model-directed ToolError and raise it."""
        raise translate_error(
            exc=exc,
            tool_name=tool_name,
            project=project,
            resource_name=resource_name,
        )

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register tool(s) with FastMCP instance."""
        pass
