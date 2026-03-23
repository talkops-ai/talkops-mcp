"""Base class for all prompts."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BasePrompt(ABC):
    """Abstract base class for all prompts.
    
    Subclasses implement specific prompt logic while inheriting
    common patterns like dependency injection.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize prompt with service locator.
        
        Args:
            service_locator: Dictionary of services (argo_service, traefik_service, config, etc.)
        """
        self.argo_service = service_locator.get('argo_service')
        self.traefik_service = service_locator.get('traefik_service')
        self.config = service_locator.get('config')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass
