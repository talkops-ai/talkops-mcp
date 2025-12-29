"""Base class for all tools."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from argoflow_mcp_server.config import ServerConfig


class BaseTool(ABC):
    """Abstract base class for all tools.
    
    Subclasses implement specific tool logic while inheriting
    common patterns like dependency injection and service access.
    
    All tools have access to:
    - argo_service: Argo Rollouts operations
    - traefik_service: Traefik traffic management operations
    - k8s_service: Kubernetes API operations
    - validation_service: Input validation and schema validation
    - config: Server configuration
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.
        
        Args:
            service_locator: Dictionary of services providing:
                - argo_service: ArgoRollouts service for rollout operations
                - traefik_service: Traefik service for traffic management
                - k8s_service: Kubernetes service for cluster operations
                - validation_service: Validation service for input validation
                - generator_service: Generator service for Deployment->Rollout conversion
                - orchestration_service: Orchestration service for intelligent deployments
                - config: ServerConfig instance
        """
        self.argo_service = service_locator.get('argo_service')
        self.traefik_service = service_locator.get('traefik_service')
        self.k8s_service = service_locator.get('k8s_service')
        self.validation_service = service_locator.get('validation_service')
        self.generator_service = service_locator.get('generator_service')
        self.orchestration_service = service_locator.get('orchestration_service')
        self.config: ServerConfig = service_locator.get('config')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register tool with FastMCP instance.
        
        Each tool must implement this method to register itself with the MCP server.
        This method should define the tool's interface, parameters, and execution logic.
        
        Args:
            mcp_instance: FastMCP server instance to register the tool with
        
        Example:
            @mcp_instance.tool()
            def my_tool(param1: str, param2: int):
                '''Tool description'''
                # Tool implementation
                return result
        """
        pass


