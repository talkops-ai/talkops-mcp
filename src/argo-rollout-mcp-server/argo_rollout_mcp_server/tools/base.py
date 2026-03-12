"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from argo_rollout_mcp_server.config import ServerConfig


class BaseTool(ABC):
    """Abstract base class for all tools.
    
    Subclasses implement specific tool logic while inheriting
    common patterns like dependency injection and service access.
    
    All tools have access to:
    - argo_service: Argo Rollouts operations
    - generator_service: Generator service for Deployment->Rollout conversion
    - orchestration_service: Orchestration service for intelligent deployments
    - config: Server configuration
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.
        
        Args:
            service_locator: Dictionary of services providing:
                - argo_service: ArgoRollouts service for rollout operations
                - generator_service: Generator service for Deployment->Rollout conversion
                - orchestration_service: Orchestration service for intelligent deployments
                - config: ServerConfig instance
        """
        self.argo_service = service_locator.get('argo_service')
        self.generator_service = service_locator.get('generator_service')
        self.orchestration_service = service_locator.get('orchestration_service')
        self.config: ServerConfig = service_locator.get('config')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register tool with FastMCP instance."""
        pass
