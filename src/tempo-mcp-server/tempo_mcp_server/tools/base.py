"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from tempo_mcp_server.config import ServerConfig
from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.services.kubernetes_service import KubernetesService


class BaseTool(ABC):
    """Abstract base class for all tools.

    Subclasses implement specific tool logic while inheriting
    common patterns like dependency injection.
    """

    tempo_service: TempoService
    kubernetes_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.

        Args:
            service_locator: Dictionary of services (tempo_service, kubernetes_service, config, etc.)

        Raises:
            RuntimeError: If required services (tempo_service, config) are missing.
        """
        tempo_service = service_locator.get("tempo_service")
        if tempo_service is None:
            raise RuntimeError(
                "tempo_service not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.tempo_service: TempoService = tempo_service

        config = service_locator.get("config")
        if config is None:
            raise RuntimeError(
                "config not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.config: ServerConfig = config

        # kubernetes_service is optional — not all tools need it
        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tool with FastMCP instance.

        Args:
            mcp_instance: FastMCP server instance
        """
        pass
