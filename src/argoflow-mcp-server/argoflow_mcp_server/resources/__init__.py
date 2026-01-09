"""Resources module for ArgoFlow MCP Server.

This module provides MCP resources for real-time monitoring and insights:
- Rollout status and progress
- Traffic distribution
- Deployment health
- Performance metrics
- Anomaly detection
- Deployment history
- Cluster health
- Cost analytics
"""

from typing import Dict, Any
from argoflow_mcp_server.resources.registry import ResourceRegistry
from argoflow_mcp_server.resources.rollout_resources import RolloutResources
from argoflow_mcp_server.resources.traffic_resources import TrafficResources
from argoflow_mcp_server.resources.health_resources import HealthResources
from argoflow_mcp_server.resources.metrics_resources import MetricsResources
from argoflow_mcp_server.resources.anomaly_resources import AnomalyResources
from argoflow_mcp_server.resources.history_resources import HistoryResources
from argoflow_mcp_server.resources.cluster_resources import ClusterResources
from argoflow_mcp_server.resources.cost_resources import CostResources


__all__ = [
    'ResourceRegistry',
    'RolloutResources',
    'TrafficResources',
    'HealthResources',
    'MetricsResources',
    'AnomalyResources',
    'HistoryResources',
    'ClusterResources',
    'CostResources',
    'initialize_resources',
]


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize and register all resources.
    
    Args:
        service_locator: Dictionary containing services (argo_service, traefik_service, config)
    
    Returns:
        ResourceRegistry with all resources registered
    
    Example:
        >>> service_locator = {
        ...     'argo_service': argo_service,
        ...     'traefik_service': traefik_service,
        ...     'config': config
        ... }
        >>> registry = initialize_resources(service_locator)
        >>> registry.register_all_resources(mcp_instance)
    """
    registry = ResourceRegistry(service_locator)
    
    # Register all resource types
    registry.register_resource(RolloutResources(service_locator))
    registry.register_resource(TrafficResources(service_locator))
    registry.register_resource(HealthResources(service_locator))
    registry.register_resource(MetricsResources(service_locator))
    registry.register_resource(AnomalyResources(service_locator))
    registry.register_resource(HistoryResources(service_locator))
    registry.register_resource(ClusterResources(service_locator))
    registry.register_resource(CostResources(service_locator))
    
    return registry
