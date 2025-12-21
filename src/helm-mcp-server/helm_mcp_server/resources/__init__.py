"""Resources module initialization."""

from typing import Dict, Any
from helm_mcp_server.resources.registry import ResourceRegistry
from helm_mcp_server.resources.helm_resources import HelmResources
from helm_mcp_server.resources.chart_resources import ChartResources
from helm_mcp_server.resources.kubernetes_resources import KubernetesResources
from helm_mcp_server.resources.static_resources import StaticResources


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resource modules.
    
    Args:
        service_locator: Dictionary of services
    
    Returns:
        Resource registry with all resources registered
    """
    registry = ResourceRegistry(service_locator)
    
    # Register resource groups
    registry.register_resource(HelmResources(service_locator))
    registry.register_resource(ChartResources(service_locator))
    registry.register_resource(KubernetesResources(service_locator))
    registry.register_resource(StaticResources(service_locator))
    
    return registry

