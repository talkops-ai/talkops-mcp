"""Base class for all resources."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseResource(ABC):
    """Abstract base class for all resources.
    
    Subclasses implement specific resource logic while inheriting
    common patterns like dependency injection.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize resource with service locator.
        
        Args:
            service_locator: Dictionary of services (helm_service, k8s_service, validation_service, etc.)
        """
        self.helm_service = service_locator.get('helm_service')
        self.k8s_service = service_locator.get('k8s_service')
        self.validation_service = service_locator.get('validation_service')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass

