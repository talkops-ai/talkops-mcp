"""Resource registry for managing Traefik MCP resources."""

from typing import Any, Dict, List
from traefik_mcp_server.resources.base import BaseResource
from traefik_mcp_server.resources.traefik_resources import TraefikResources


class ResourceRegistry:
    """Registry for managing and registering Traefik MCP resources."""

    def __init__(self, service_locator: Dict[str, Any]) -> None:
        self.service_locator = service_locator
        self.resources: List[BaseResource] = []

    def register_resource(self, resource: BaseResource) -> None:
        self.resources.append(resource)

    def register_all_resources(self, mcp_instance: Any) -> None:
        for resource in self.resources:
            resource.register(mcp_instance)

    def get_resources_count(self) -> int:
        return len(self.resources)

    def get_resources(self) -> List[BaseResource]:
        return self.resources.copy()


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize and return the ResourceRegistry with all 12 traefik:// resources."""
    registry = ResourceRegistry(service_locator)
    registry.register_resource(TraefikResources(service_locator))
    return registry
