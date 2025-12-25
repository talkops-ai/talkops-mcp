"""Base class for all prompts."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from argocd_mcp_server.config import ServerConfig


class BasePrompt(ABC):
    """Abstract base class for all prompts.
    
    Subclasses implement specific guided workflow logic while inheriting
    common patterns like dependency injection.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize prompt with service locator.
        
        Args:
            service_locator: Dictionary of services (argocd_service, config, etc.)
        """
        self.argocd_service = service_locator.get('argocd_service')
        self.config: ServerConfig = service_locator.get('config')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register prompt with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass
