"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from opentelemetry_mcp_server.config import ServerConfig
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)


class BaseTool(ABC):
    """Abstract base class for all tools.

    Subclasses implement specific tool logic while inheriting
    common patterns like dependency injection.
    """

    kubernetes_service: KubernetesService
    collector_config_service: CollectorConfigService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.

        Args:
            service_locator: Dictionary of services.
        """
        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]
        self.collector_config_service = service_locator.get("collector_config_service")  # type: ignore[assignment]
        self.config = service_locator.get("config")  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tool with FastMCP instance.

        Args:
            mcp_instance: FastMCP server instance.
        """
        pass
