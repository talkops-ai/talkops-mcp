"""Base class for all ArgoCD MCP resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict
from argocd_mcp_server.config import ServerConfig


class BaseResource(ABC):
    """Abstract base class for all resources."""

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize resource with service locator."""
        self.service_locator = service_locator
        self.argocd_service: Any = service_locator.get("argocd_service")
        self.mgmt_service: Any = service_locator.get("mgmt_service")
        self.config: Any = service_locator.get("config")

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        """Register resource with FastMCP instance."""
        pass
