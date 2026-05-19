"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from prometheus_mcp_server.config import ServerConfig
from prometheus_mcp_server.services.prometheus_service import PrometheusService
from prometheus_mcp_server.services.kubernetes_service import KubernetesService


class BaseTool(ABC):
    """Abstract base class for all tools.

    Subclasses implement specific tool logic while inheriting
    common patterns like dependency injection.
    """

    prometheus_service: PrometheusService
    kubernetes_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.

        Args:
            service_locator: Dictionary of services (prometheus_service, kubernetes_service, config, etc.)
        """
        self.prometheus_service = service_locator.get('prometheus_service')  # type: ignore[assignment]
        self.kubernetes_service = service_locator.get('kubernetes_service')  # type: ignore[assignment]
        self.config = service_locator.get('config')  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tool with FastMCP instance.

        Args:
            mcp_instance: FastMCP server instance
        """
        pass
