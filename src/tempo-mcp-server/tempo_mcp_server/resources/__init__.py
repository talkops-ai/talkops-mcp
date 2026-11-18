"""Resources module initialization — strictly live/dynamic resources."""

from typing import Any, Dict

from tempo_mcp_server.resources.backend_resources import BackendResources
from tempo_mcp_server.resources.deployment_resources import DeploymentResources
from tempo_mcp_server.resources.registry import ResourceRegistry


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all dynamic resource modules."""
    registry = ResourceRegistry(service_locator)
    registry.register_resource(BackendResources(service_locator))
    registry.register_resource(DeploymentResources(service_locator))
    return registry
