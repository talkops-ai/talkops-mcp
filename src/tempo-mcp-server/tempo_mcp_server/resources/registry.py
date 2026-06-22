"""Resource registry for managing all resources."""

from typing import Any, Dict, List
from tempo_mcp_server.resources.base import BaseResource


class ResourceRegistry:
    """Registry for managing resources."""

    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.resources: List[BaseResource] = []

    def register_resource(self, resource: BaseResource) -> None:
        self.resources.append(resource)

    def register_all_resources(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        for resource in self.resources:
            resource.register(mcp_instance)
