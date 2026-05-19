"""Base class for all resources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from helm_mcp_server.services.helm_service import HelmService
    from helm_mcp_server.services.kubernetes_service import KubernetesService
    from helm_mcp_server.services.validation_service import ValidationService


class BaseResource(ABC):
    """Abstract base class for all resources.
    
    Subclasses implement specific resource logic while inheriting
    common patterns like dependency injection.
    """
    
    helm_service: HelmService
    k8s_service: KubernetesService
    validation_service: ValidationService
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize resource with service locator.
        
        Args:
            service_locator: Dictionary of services (helm_service, k8s_service, validation_service, etc.)
        """
        self.helm_service = service_locator.get('helm_service')  # type: ignore[assignment]
        self.k8s_service = service_locator.get('k8s_service')  # type: ignore[assignment]
        self.validation_service = service_locator.get('validation_service')  # type: ignore[assignment]
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass
