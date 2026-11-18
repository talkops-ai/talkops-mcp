"""Base class for all execution-layer MCP tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from fastmcp import Context
    from helm_mcp_server.config import ServerConfig
    from helm_mcp_server.services.helm_service import HelmService
    from helm_mcp_server.services.kubernetes_service import KubernetesService


class BaseTool(ABC):
    """Abstract base class for all tools with dependency injection and session helpers."""

    helm_service: HelmService
    k8s_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator."""
        self.helm_service = service_locator.get("helm_service")  # type: ignore[assignment]
        self.k8s_service = service_locator.get("k8s_service")  # type: ignore[assignment]
        self.config = service_locator.get("config")  # type: ignore[assignment]

    @staticmethod
    def _get_session_id(ctx: Optional[Context]) -> Optional[str]:
        """Extract stable session identifier from FastMCP Context when available."""
        if ctx is None:
            return None
        try:
            session_id = getattr(ctx, "session_id", None)
            if isinstance(session_id, str) and session_id:
                return session_id
        except Exception:
            pass
        return None

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register tool group with FastMCP instance."""
        pass
