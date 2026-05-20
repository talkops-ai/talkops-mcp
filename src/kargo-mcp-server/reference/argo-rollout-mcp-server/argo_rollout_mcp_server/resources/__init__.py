"""Resources module for Argo Rollout MCP Server.

Provides MCP resources for real-time monitoring and insights:
- Rollout status and progress
- Deployment health
- Performance metrics
- Deployment history
- Cluster health
"""

from typing import Dict, Any
from argo_rollout_mcp_server.resources.registry import ResourceRegistry
from argo_rollout_mcp_server.resources.rollout_resources import RolloutResources
from argo_rollout_mcp_server.resources.health_resources import HealthResources
from argo_rollout_mcp_server.resources.metrics_resources import MetricsResources
from argo_rollout_mcp_server.resources.history_resources import HistoryResources
from argo_rollout_mcp_server.resources.cluster_resources import ClusterResources


__all__ = [
    'ResourceRegistry',
    'RolloutResources',
    'HealthResources',
    'MetricsResources',
    'HistoryResources',
    'ClusterResources',
    'initialize_resources',
]


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize and register all resources.
    
    Args:
        service_locator: Dictionary containing services (argo_service, config)
    
    Returns:
        ResourceRegistry with all resources registered
    """
    registry = ResourceRegistry(service_locator)
    
    # Register Argo Rollout resource types (no traffic, anomaly, or migration resources)
    registry.register_resource(RolloutResources(service_locator))
    registry.register_resource(HealthResources(service_locator))
    registry.register_resource(MetricsResources(service_locator))
    registry.register_resource(HistoryResources(service_locator))
    registry.register_resource(ClusterResources(service_locator))
    
    return registry
