"""Base class and helper functions for all Traefik MCP Server tools."""

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

from traefik_mcp_server.config import ServerConfig
from traefik_mcp_server.exceptions.custom import (
    KubernetesNamespaceError,
    KubernetesOperationError,
    KubernetesResourceError,
    TraefikCircuitBreakerError,
    TraefikEmptyBackendError,
    TraefikMiddlewareError,
    TraefikMirroringError,
    TraefikOperationError,
    TraefikOwnershipError,
    TraefikReferentialIntegrityError,
    TraefikRouteConfigError,
    TraefikRouteNotFoundError,
    TraefikSchemaGatingError,
    TraefikServiceError,
    TraefikSSRFBlockedError,
    TraefikTLSError,
    TraefikWeightError,
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
                f"Read 'traefik://routes/{namespace}' or 'traefik://policies/{namespace}' to verify valid names."
            )
        if exc.status == 403:
            return ToolError(
                f"RBAC permission denied in namespace '{namespace}' during {tool_name} ({exc.reason}). "
                "Verify the Kubernetes ServiceAccount or kubeconfig user has permissions on traefik.io CRDs and core Services."
            )
        if exc.status == 409:
            return ToolError(
                f"Resource conflict on '{target}' in namespace '{namespace}' ({exc.reason}). "
                f"Read 'traefik://manifests/IngressRoute/{namespace}/{target}' or re-run with dry_run=True to get the latest resourceVersion."
            )
        if exc.status == 422:
            return ToolError(
                f"Kubernetes schema validation failed on '{target}' ({exc.reason}). "
                f"Read 'traefik://schema/IngressRoute' or call traefik_diagnose_route(name='{target}', namespace='{namespace}') to inspect spec errors."
            )

    if isinstance(exc, TraefikRouteNotFoundError):
        return ToolError(
            f"{msg}. Read 'traefik://routes/{namespace}' or 'traefik://policies/{namespace}' "
            f"to verify valid resource names in namespace '{namespace}'."
        )
    if isinstance(exc, TraefikOwnershipError):
        return ToolError(
            f"{msg}. Read 'traefik://routes/{namespace}' to inspect ownership metadata "
            "or use the owning controller's MCP tools."
        )
    if isinstance(exc, TraefikSchemaGatingError):
        return ToolError(
            f"{msg}. Read 'traefik://schema/Middleware' or 'traefik://server/capabilities' "
            "to inspect supported fields for this cluster's Traefik CRD version."
        )
    if isinstance(exc, TraefikEmptyBackendError):
        return ToolError(
            f"{msg}. Call traefik_diagnose_route(name='{target}', namespace='{namespace}') "
            "to verify backend Service and EndpointSlice readiness before shifting traffic weight."
        )
    if isinstance(exc, TraefikReferentialIntegrityError):
        return ToolError(
            f"{msg}. Read 'traefik://policies/{namespace}' and 'traefik://certificates/{namespace}' "
            f"or call traefik_diagnose_route(name='{target}', namespace='{namespace}') to verify referenced objects."
        )
    if isinstance(exc, TraefikSSRFBlockedError):
        return ToolError(
            f"{msg}. Read 'traefik://routes/_all' to find valid cluster route hostnames, "
            "or start the server with --probe-allow-any-host if external probing is intended."
        )
    if isinstance(exc, (TraefikMiddlewareError, TraefikCircuitBreakerError)):
        return ToolError(
            f"{msg}. Read 'traefik://policies/{namespace}' or 'traefik://schema/Middleware' "
            "to verify valid middleware specifications."
        )
    if isinstance(exc, (TraefikWeightError, TraefikMirroringError, TraefikServiceError)):
        return ToolError(
            f"{msg}. Read 'traefik://routes/{namespace}' or call "
            f"traefik_diagnose_route(kind='TraefikService', name='{target}', namespace='{namespace}') to inspect service weights."
        )
    if isinstance(exc, (TraefikRouteConfigError, TraefikTLSError)):
        return ToolError(
            f"{msg}. Read 'traefik://instance/static-config' and 'traefik://certificates/{namespace}' "
            "to verify entryPoints, certResolvers, and TLS secrets."
        )
    if isinstance(exc, (KubernetesResourceError, KubernetesOperationError, KubernetesNamespaceError)):
        return ToolError(
            f"{msg}. Read 'traefik://server/capabilities' and 'traefik://cluster/contexts' "
            "to verify cluster connectivity, watched namespaces, and installed Traefik CRDs."
        )
    if isinstance(exc, (ValueError, TraefikOperationError)):
        if "not found" in msg.lower():
            return ToolError(
                f"{msg}. Read 'traefik://routes/{namespace}' or 'traefik://policies/{namespace}' "
                f"in namespace '{namespace}' before retrying."
            )
        return ToolError(
            f"{msg}. Read 'traefik://routes/{namespace}' or call "
            f"traefik_diagnose_route(name='{target}', namespace='{namespace}') to inspect current state."
        )

    return ToolError(
        f"{tool_name} failed: {msg}. Read 'traefik://routes/{namespace}' or call "
        f"traefik_diagnose_route(name='{target}', namespace='{namespace}') to diagnose cluster state."
    )


class BaseTool(ABC):
    """Abstract base class for all tools with write gates, elicitation, and error translation."""

    def __init__(self, service_locator: Dict[str, Any]):
        self.traefik_service = service_locator.get("traefik_service")
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
                "MCP_ALLOW_WRITE=true to enable cluster mutations, or use read-only resources "
                "(traefik://routes/_all) and diagnostic tools (traefik_diagnose_route)."
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
