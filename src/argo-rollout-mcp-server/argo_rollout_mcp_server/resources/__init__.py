"""Resources module for Argo Rollout MCP Server.

Exposes 13 clean MCP resources across Rollouts, Analysis, History, Metrics, Cluster, and Server capabilities.
"""

from typing import Any, Dict
from argo_rollout_mcp_server.resources.cluster_resources import ClusterResources
from argo_rollout_mcp_server.resources.history_resources import HistoryResources
from argo_rollout_mcp_server.resources.metrics_resources import MetricsResources
from argo_rollout_mcp_server.resources.registry import ResourceRegistry
from argo_rollout_mcp_server.resources.rollout_resources import RolloutResources

__all__ = [
    "ResourceRegistry",
    "RolloutResources",
    "MetricsResources",
    "HistoryResources",
    "ClusterResources",
    "initialize_resources",
]


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize and register all 13 MCP resources."""
    registry = ResourceRegistry(service_locator)
    registry.register_resource(RolloutResources(service_locator))
    registry.register_resource(MetricsResources(service_locator))
    registry.register_resource(HistoryResources(service_locator))
    registry.register_resource(ClusterResources(service_locator))
    return registry
