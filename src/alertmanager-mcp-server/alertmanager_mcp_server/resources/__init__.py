"""Resources module for Alertmanager MCP server."""
from typing import Any, Dict, List
from alertmanager_mcp_server.resources.base import BaseResource


class ResourceRegistry:
    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.resources: List[BaseResource] = []

    def register_resource(self, resource: BaseResource) -> None:
        self.resources.append(resource)

    def register_all_resources(self, mcp_instance) -> None:
        for resource in self.resources:
            resource.register(mcp_instance)


from alertmanager_mcp_server.resources.backend_resources import BackendResources
from alertmanager_mcp_server.resources.alert_resources import AlertResources
from alertmanager_mcp_server.resources.silence_resources import SilenceResources
from alertmanager_mcp_server.resources.config_resources import ConfigResources
from alertmanager_mcp_server.resources.static_resources import StaticResources
from alertmanager_mcp_server.resources.audit_resources import AuditResources
from alertmanager_mcp_server.resources.status_resources import StatusResources


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    registry = ResourceRegistry(service_locator)
    registry.register_resource(BackendResources(service_locator))
    registry.register_resource(AlertResources(service_locator))
    registry.register_resource(SilenceResources(service_locator))
    registry.register_resource(ConfigResources(service_locator))
    registry.register_resource(StaticResources(service_locator))
    registry.register_resource(AuditResources(service_locator))
    registry.register_resource(StatusResources(service_locator))
    return registry
