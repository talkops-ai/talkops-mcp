"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from argocd_mcp_server.config import ServerConfig


class BaseTool(ABC):
    """Abstract base class for all tools.
    
    Subclasses implement specific tool logic while inheriting
    common patterns like dependency injection.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.
        
        Args:
            service_locator: Dictionary of services (argocd_service, config, etc.)
        """
        self.argocd_service = service_locator.get('argocd_service')
        self.config: ServerConfig = service_locator.get('config')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register tool with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass
