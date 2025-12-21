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
            service_locator: Dictionary of services (helm_service, k8s_service, validation_service, etc.)
        """
        self.helm_service = service_locator.get('helm_service')
        self.k8s_service = service_locator.get('k8s_service')
        self.validation_service = service_locator.get('validation_service')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass

