"""Resources module for Traefik MCP Server.

Provides MCP resources for real-time monitoring and insights:
- Traffic distribution and routes
- Metrics summary
- Anomaly detection
- Migration workflows
"""

from typing import Dict, Any, List

from traefik_mcp_server.resources.registry import ResourceRegistry
from traefik_mcp_server.resources.base import BaseResource
from traefik_mcp_server.resources.traffic_resources import TrafficResources
from traefik_mcp_server.resources.metrics_resources import MetricsResources
from traefik_mcp_server.resources.anomaly_resources import AnomalyResources
from traefik_mcp_server.resources.migration_resources import MigrationResources

__all__ = [
    'initialize_resources',
    'ResourceRegistry',
    'BaseResource',
    'TrafficResources',
    'MetricsResources',
    'AnomalyResources',
    'MigrationResources',
]


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resources and register them with the registry.
    
    Args:
        service_locator: Dictionary containing service instances
        
    Returns:
        Configured ResourceRegistry
    """
    registry = ResourceRegistry(service_locator)
    
    # Initialize resource categories
    resources: List[BaseResource] = [
        TrafficResources(service_locator),
        MetricsResources(service_locator),
        AnomalyResources(service_locator),
        MigrationResources(service_locator),
    ]
    
    # Add to registry
    for resource in resources:
        registry.register_resource(resource)
        
    return registry
