"""Base class for all MCP resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseResource(ABC):
    """Abstract base class for MCP resources."""

    def __init__(self, service_locator: Dict[str, Any]) -> None:
        self.traefik_service = service_locator.get("traefik_service")
        self.config = service_locator.get("config")

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register resources with FastMCP instance."""
        pass
