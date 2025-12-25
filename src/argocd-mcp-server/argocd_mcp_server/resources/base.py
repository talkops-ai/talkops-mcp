"""Base class for all resources."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from argocd_mcp_server.config import ServerConfig


class BaseResource(ABC):
    """Abstract base class for all resources.
    
    Subclasses implement specific resource logic while inheriting
    common patterns like dependency injection.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize resource with service locator.
        
        Args:
            service_locator: Dictionary of services (argocd_service, config, etc.)
        """
        self.argocd_service = service_locator.get('argocd_service')
        self.config: ServerConfig = service_locator.get('config')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register resource with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass
