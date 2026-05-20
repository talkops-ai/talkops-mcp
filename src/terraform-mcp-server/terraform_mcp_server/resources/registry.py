"""Resource registry for managing all Terraform MCP resources."""

from typing import Dict, Any, List
from terraform_mcp_server.resources.base import BaseResource


class ResourceRegistry:
    """Registry for managing MCP resources.
    
    Centralizes resource registration and provides bulk registration
    with the FastMCP instance.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize registry with service locator.
        
        Args:
            service_locator: Dependency injection container
        """
        self.service_locator = service_locator
        self.resources: List[BaseResource] = []
    
    def register_resource(self, resource: BaseResource) -> None:
        """Register a resource with the registry.
        
        Args:
            resource: Resource instance inheriting from BaseResource
        """
        self.resources.append(resource)
    
    def register_all_resources(self, mcp_instance) -> None:
        """Register all resources with the FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        for resource in self.resources:
            resource.register(mcp_instance)
