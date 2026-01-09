"""Resource registry for managing all resources."""

from typing import Dict, Any, List
from argoflow_mcp_server.resources.base import BaseResource


class ResourceRegistry:
    """Registry for managing resources.
    
    Encapsulates resource registration and lifecycle.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize registry.
        
        Args:
            service_locator: Dictionary of services
        """
        self.service_locator = service_locator
        self.resources: List[BaseResource] = []
    
    def register_resource(self, resource: BaseResource) -> None:
        """Register a resource.
        
        Args:
            resource: Resource instance
        """
        self.resources.append(resource)
    
    def register_all_resources(self, mcp_instance) -> None:
        """Register all resources with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        for resource in self.resources:
            resource.register(mcp_instance)
