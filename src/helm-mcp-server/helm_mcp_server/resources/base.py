"""Base class for all MCP resources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from helm_mcp_server.services.helm_service import HelmService
    from helm_mcp_server.services.kubernetes_service import KubernetesService


class BaseResource(ABC):
    """Abstract base class for all URI-addressed MCP resources."""

    helm_service: HelmService
    k8s_service: KubernetesService

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize resource with service locator."""
        self.helm_service = service_locator.get("helm_service")  # type: ignore[assignment]
        self.k8s_service = service_locator.get("k8s_service")  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register resources with FastMCP instance."""
        pass
