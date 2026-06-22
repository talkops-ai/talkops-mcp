"""Base class for all Loki MCP tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from loki_mcp_server.config import ServerConfig
from loki_mcp_server.services.loki_service import LokiService


class BaseTool(ABC):
    """Abstract base class for all Loki MCP tools.

    Subclasses implement specific tool logic while inheriting
    dependency injection via the service_locator pattern.
    """

    loki_service: LokiService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.

        Args:
            service_locator: Dictionary of shared services.

        Raises:
            RuntimeError: If required services (loki_service, config) are missing.
        """
        loki_service = service_locator.get("loki_service")
        if loki_service is None:
            raise RuntimeError(
                "loki_service not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.loki_service: LokiService = loki_service

        config = service_locator.get("config")
        if config is None:
            raise RuntimeError(
                "config not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.config: ServerConfig = config

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tool(s) with the FastMCP instance.

        Args:
            mcp_instance: FastMCP server instance.
        """
        pass
