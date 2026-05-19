"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Dict, Any

from kargo_mcp_server.config import ServerConfig
from kargo_mcp_server.services.kargo_service import KargoService


class BaseTool(ABC):
    """Abstract base class for all tools.

    Subclasses implement specific tool logic while inheriting
    common patterns like dependency injection.
    """

    kargo_service: KargoService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.

        Args:
            service_locator: Dictionary of services (kargo_service, config, etc.)
        """
        self.kargo_service = service_locator.get('kargo_service')  # type: ignore[assignment]
        self.config = service_locator.get('config')  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tool with FastMCP instance.

        Args:
            mcp_instance: FastMCP server instance
        """
        pass
