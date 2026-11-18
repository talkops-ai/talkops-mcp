"""Base class and helper functions for all Argo Rollout MCP Server tools."""

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

from argo_rollout_mcp_server.config import ServerConfig
from argo_rollout_mcp_server.exceptions.custom import (
    AnalysisTemplateError,
    ArgoRolloutError,
    KubernetesOperationError,
    KubernetesResourceError,
    RolloutAbortError,
    RolloutNotFoundError,
    RolloutPromotionError,
    RolloutStrategyError,
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
                f"Read 'argorollout://rollouts/list' or 'argorollout://cluster/namespaces' to verify valid names."
            )
        if exc.status == 403:
            return ToolError(
                f"RBAC permission denied in namespace '{namespace}' during {tool_name} ({exc.reason}). "
                "Verify the Kubernetes ServiceAccount or kubeconfig user has permissions on argoproj.io and core Services."
            )
        if exc.status == 409:
            return ToolError(
                f"Resource conflict on '{target}' in namespace '{namespace}' ({exc.reason}). "
                f"Read 'argorollout://rollouts/{namespace}/{target}/detail' and retry."
            )
        if exc.status == 422:
            return ToolError(
                f"Kubernetes schema validation failed on '{target}' ({exc.reason}). "
                f"Call argo_diagnose_rollout(name='{target}', namespace='{namespace}') to inspect spec errors."
            )

    if isinstance(exc, RolloutNotFoundError):
        return ToolError(
            f"{msg}. Read 'argorollout://rollouts/list' or 'argorollout://cluster/namespaces' "
            f"to verify valid Rollout and Experiment names in namespace '{namespace}'."
        )
    if isinstance(exc, (RolloutPromotionError, RolloutAbortError)):
        return ToolError(
            f"{msg}. Call argo_diagnose_rollout(name='{target}', namespace='{namespace}') "
            f"or read 'argorollout://rollouts/{namespace}/{target}/detail' to inspect current phase, "
            "step index, and pauseConditions."
        )
    if isinstance(exc, RolloutStrategyError):
        return ToolError(
            f"{msg}. Call argo_diagnose_rollout(name='{target}', namespace='{namespace}') or read "
            f"'argorollout://rollouts/{namespace}/{target}/detail' to check active strategy, "
            f"or call argo_configure_rollout_strategy(name='{target}', namespace='{namespace}', "
            "repair_conflicts=True) if conflicting strategy blocks exist."
        )
    if isinstance(exc, AnalysisTemplateError):
        return ToolError(
            f"{msg}. Read 'argorollout://analysistemplates/{namespace}' and "
            "'argorollout://metrics/prometheus/status' to verify available templates and Prometheus status."
        )
    if isinstance(exc, (KubernetesResourceError, KubernetesOperationError)):
        return ToolError(
            f"{msg}. Read 'argorollout://server/capabilities' and 'argorollout://cluster/contexts' "
            "to verify cluster connectivity and installed Argo Rollouts CRDs."
        )
    if isinstance(exc, (ValueError, ArgoRolloutError)):
        if "not found" in msg.lower():
            return ToolError(
                f"{msg}. Read 'argorollout://rollouts/list' or 'argorollout://cluster/namespaces' "
                f"in namespace '{namespace}' before retrying."
            )
        return ToolError(
            f"{msg}. Read 'argorollout://rollouts/{namespace}/{target}/detail' or "
            "'argorollout://rollouts/list' to inspect current state."
        )

    return ToolError(
        f"{tool_name} failed: {msg}. Read 'argorollout://rollouts/list' or call "
        f"argo_diagnose_rollout(name='{target}', namespace='{namespace}') to diagnose cluster state."
    )


class BaseTool(ABC):
    """Abstract base class for all tools with write gates, elicitation, and error translation."""

    def __init__(self, service_locator: Dict[str, Any]):
        self.argo_service = service_locator.get("argo_service")
        self.generator_service = service_locator.get("generator_service")
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
                "(argorollout://rollouts/list) and diagnostic tools (argo_diagnose_rollout)."
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
