"""Resource registry for managing all resources."""

from typing import Dict, Any, List
from argo_rollout_mcp_server.resources.base import BaseResource


class ResourceRegistry:
    """Registry for managing resources."""
    
    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.resources: List[BaseResource] = []
    
    def register_resource(self, resource: BaseResource) -> None:
        self.resources.append(resource)
    
    def register_all_resources(self, mcp_instance) -> None:
        for resource in self.resources:
            resource.register(mcp_instance)
