"""Resources module initialization."""

from typing import Any, Dict

from loki_mcp_server.resources.registry import ResourceRegistry
from loki_mcp_server.resources.loki_resources import LokiResources


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resources and return the registry."""
    registry = ResourceRegistry(service_locator)
    registry.register_resource(LokiResources(service_locator))
    return registry
