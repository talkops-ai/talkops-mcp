"""Base class and helper functions for all OpenTelemetry MCP Server tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Literal, Optional

from fastmcp import Context
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from kubernetes.client.rest import ApiException

from opentelemetry_mcp_server.config import ServerConfig
from opentelemetry_mcp_server.exceptions import (
    OtelConfigParseError,
    OtelConnectionError,
    OtelOperationError,
    OtelResourceError,
    OtelResourceNotFoundError,
    OtelValidationError,
)
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService


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
            elicitation = await ctx.elicit(
                f"Confirm destructive operation: {action_summary}?",
                response_type=Literal["confirm", "abort"],
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
    namespace: str = "default",
    resource_name: Optional[str] = None,
) -> ToolError:
    """Translate domain and Kubernetes exceptions into model-directed ToolError feedback."""
    if type(exc) is ToolError:
        return exc

    target = resource_name or "<name>"
    msg = str(exc)

    if isinstance(exc, ApiException):
        if exc.status == 404:
            return ToolError(
                f"Resource '{target}' not found in namespace '{namespace}' ({exc.reason}). "
                f"Read 'otel://collectors/{namespace}' or 'otel://instrumentations/{namespace}' "
                f"or call otel_survey_cluster(namespaces=['{namespace}']) to verify valid names."
            )
        if exc.status == 403:
            return ToolError(
                f"RBAC permission denied in namespace '{namespace}' during {tool_name} ({exc.reason}). "
                "Verify the Kubernetes ServiceAccount or kubeconfig user has permissions on "
                "opentelemetry.io CRDs and core/apps resources."
            )
        if exc.status == 409:
            return ToolError(
                f"Resource conflict on '{target}' in namespace '{namespace}' ({exc.reason}). "
                f"Read 'otel://collector/{namespace}/{target}' and retry."
            )
        if exc.status == 422:
            return ToolError(
                f"Kubernetes schema validation failed on '{target}' ({exc.reason}). "
                f"Call otel_validate_collector_config(namespace='{namespace}', name='{target}') "
                "to inspect configuration errors."
            )

    if isinstance(exc, OtelResourceNotFoundError) or "not found" in msg.lower():
        return ToolError(
            f"{msg}. Read 'otel://collectors/{namespace}' or 'otel://instrumentations/{namespace}' "
            f"or call otel_list_workloads(namespace='{namespace}') to verify valid names."
        )
    if isinstance(exc, (OtelValidationError, OtelConfigParseError)):
        return ToolError(
            f"{msg}. Call otel_validate_collector_config(namespace='{namespace}', name='{target}') "
            "or review the tool parameter schema before retrying."
        )
    if isinstance(exc, OtelConnectionError):
        return ToolError(
            f"{msg}. Read 'otel://server/capabilities' and 'otel://operator/status' "
            "to verify Kubernetes connectivity and OpenTelemetry Operator installation."
        )
    if isinstance(exc, (OtelOperationError, OtelResourceError, ValueError)):
        return ToolError(
            f"{msg}. Read 'otel://collector/{namespace}/{target}' or call "
            f"otel_diagnose_collector(namespace='{namespace}', name='{target}') to inspect state."
        )

    return ToolError(
        f"{tool_name} failed: {msg}. Read 'otel://server/capabilities' or call "
        f"otel_diagnose_collector(namespace='{namespace}', name='{target}') to diagnose cluster state."
    )


class BaseTool(ABC):
    """Abstract base class for all tools with write gates, elicitation, and error translation."""

    kubernetes_service: KubernetesService
    collector_config_service: CollectorConfigService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator."""
        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]
        self.collector_config_service = service_locator.get("collector_config_service")  # type: ignore[assignment]
        self.config = service_locator.get("config") or ServerConfig()

    def should_register_tool(self, toolset: str, is_write: bool = False) -> bool:
        """Determine whether a tool should be registered given active toolsets and write gate."""
        active_toolsets = self.config.toolsets if self.config else ["all"]
        write_enabled = bool(self.config.write_enabled) if self.config else False

        if is_write and not write_enabled:
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
        if not self.config or not self.config.write_enabled:
            raise ToolError(
                f"Tool '{tool_name}' is blocked because the server is running in read-only mode "
                "(MCP_ALLOW_WRITE=false). Start the server with --allow-write or set "
                "MCP_ALLOW_WRITE=true to enable cluster mutations, or use read-only resources "
                "('otel://collectors/{namespace}') and diagnostic tools ('otel_diagnose_collector')."
            )

    def check_write_access(self, tool_name: str) -> None:
        """Alias for require_write_access."""
        self.require_write_access(tool_name)

    def handle_error(
        self,
        exc: Exception,
        tool_name: str,
        namespace: str = "default",
        resource_name: Optional[str] = None,
    ) -> None:
        """Translate exception into a model-directed ToolError and raise it."""
        raise translate_error(
            exc=exc,
            tool_name=tool_name,
            namespace=namespace,
            resource_name=resource_name,
        )

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register tool(s) with FastMCP instance."""
        pass
