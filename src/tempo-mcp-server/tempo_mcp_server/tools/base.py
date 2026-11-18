"""Base class, write gates, MCP elicitation, and model-directed error translation for Tempo tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Literal, Optional

from fastmcp import Context
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)

from tempo_mcp_server.config import ServerConfig
from tempo_mcp_server.exceptions.custom import (
    TempoConnectionError,
    TempoOperationError,
    TempoQueryError,
    TempoResourceNotFoundError,
    TempoTenantError,
    TempoValidationError,
)
from tempo_mcp_server.services.kubernetes_service import KubernetesService
from tempo_mcp_server.services.tempo_service import TempoService


async def confirm_destructive_action(
    ctx: Optional[Context],
    action_summary: str,
    confirm: bool = False,
) -> bool:
    """Gate mutating operations via MCP Elicitation with a confirm=True fallback.

    Returns True when confirmed and execution should proceed, or False when
    declined/cancelled or when confirm=False without interactive elicitation.
    """
    if confirm:
        return True

    if ctx is not None and hasattr(ctx, "elicit"):
        try:
            elicitation = await ctx.elicit(
                f"Confirm operation: {action_summary}?",
                response_type=["confirm", "abort"],
            )
            if isinstance(elicitation, (DeclinedElicitation, CancelledElicitation)):
                return False
            action = getattr(elicitation, "action", None)
            if action in ("decline", "cancel"):
                return False
            data = getattr(elicitation, "data", None)
            if isinstance(elicitation, AcceptedElicitation) or action == "accept":
                if data in ("confirm", True) or (isinstance(data, dict) and data.get("confirm") is True):
                    return True
                return False
        except Exception:
            # Client host does not implement an elicitation handler; fall back to confirm flag
            pass

    return False


def translate_error(
    exc: Exception,
    tool_name: str,
    backend_id: Optional[str] = None,
    namespace: str = "default",
    resource_name: Optional[str] = None,
) -> ToolError:
    """Translate Tempo and Kubernetes exceptions into model-directed recovery feedback."""
    if type(exc) is ToolError:
        return exc

    msg = str(exc)
    bid = backend_id or "default"
    target = resource_name or "<name>"

    # Kubernetes API exceptions (duck-typed on status/reason)
    status_code = getattr(exc, "status", None)
    reason = getattr(exc, "reason", None)
    if status_code is not None:
        if status_code == 404:
            return ToolError(
                f"Resource '{target}' not found in namespace '{namespace}' ({reason}). "
                f"Read 'tempo://operator/crs/{namespace}' to list existing TempoStack and TempoMonolithic CRs."
            )
        if status_code == 403:
            return ToolError(
                f"Kubernetes RBAC permission denied in namespace '{namespace}' during {tool_name} ({reason}). "
                "Read 'tempo://server/capabilities' to verify Kubernetes access."
            )
        if status_code == 409:
            return ToolError(
                f"Resource conflict on '{target}' in namespace '{namespace}' ({reason}). "
                f"Read 'tempo://operator/manifests/TempoStack/{namespace}/{target}' or run with dry_run=True."
            )
        if status_code == 422:
            return ToolError(
                f"Kubernetes CRD schema validation failed on '{target}' ({reason}): {msg}. "
                "Read 'tempo://operator/crd-schema/TempoStack' to inspect valid CRD fields."
            )

    if isinstance(exc, TempoTenantError):
        return ToolError(
            f"{msg} Read 'tempo://system/backends/{bid}' to inspect multi-tenant requirements."
        )
    if isinstance(exc, TempoQueryError):
        return ToolError(
            f"{msg} Call tempo_get_attribute_names(backend_id='{bid}') or read "
            f"'tempo://schema/{bid}/attributes' to verify valid attribute names."
        )
    if isinstance(exc, TempoConnectionError):
        return ToolError(
            f"{msg} Read 'tempo://system/backends' or call tempo_get_diagnostics(backend_id='{bid}') "
            "to check backend connectivity."
        )
    if isinstance(exc, (TempoValidationError, TempoResourceNotFoundError)):
        return ToolError(msg)

    if "unknown backend" in msg.lower():
        return ToolError(
            f"{msg}. Read 'tempo://system/backends' to list configured backend IDs."
        )
    if "412" in msg or "precondition" in msg.lower() or "etag" in msg.lower():
        return ToolError(
            f"{msg} Read 'tempo://overrides/{bid}/<tenant>' to fetch the current ETag before retrying."
        )
    if "404" in msg or "not found" in msg.lower():
        return ToolError(
            f"{msg} Read 'tempo://system/backends/{bid}' or call tempo_traceql_search(backend_id='{bid}') "
            "to locate valid trace IDs within retention."
        )

    if isinstance(exc, TempoOperationError):
        return exc

    return ToolError(
        f"{tool_name} failed: {msg}. Read 'tempo://server/capabilities' or 'tempo://system/backends' "
        "to verify backend status."
    )


class BaseTool(ABC):
    """Abstract base class for all Tempo MCP tools."""

    tempo_service: TempoService
    kubernetes_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        tempo_service = service_locator.get("tempo_service")
        if tempo_service is None:
            raise RuntimeError(
                "tempo_service not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.tempo_service = tempo_service

        config = service_locator.get("config")
        if config is None:
            raise RuntimeError(
                "config not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.config = config

        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]

    def should_register_tool(self, toolset: str, is_write: bool = False) -> bool:
        """Determine whether a tool should be registered given active toolsets and write gate."""
        if not self.config:
            return not is_write
        return self.config.should_register(toolset=toolset, is_write=is_write)

    def require_write_access(self, tool_name: str) -> None:
        """Defense-in-depth write gate enforcement."""
        if not self.config or not self.config.allow_write:
            raise ToolError(
                f"Tool '{tool_name}' is blocked because the server is running in read-only mode "
                "(MCP_ALLOW_WRITE=false). Start the server with --allow-write or set "
                "MCP_ALLOW_WRITE=true to enable state mutations, or use read-only resources "
                "('tempo://operator/crs/_all', 'tempo://overrides/{backend_id}/{tenant}')."
            )

    def handle_error(
        self,
        exc: Exception,
        tool_name: str,
        backend_id: Optional[str] = None,
        namespace: str = "default",
        resource_name: Optional[str] = None,
    ) -> None:
        """Translate exception into a model-directed ToolError and raise it."""
        raise translate_error(
            exc=exc,
            tool_name=tool_name,
            backend_id=backend_id,
            namespace=namespace,
            resource_name=resource_name,
        )

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register tool(s) with FastMCP instance."""
        pass
