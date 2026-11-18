"""Tools module initialization."""

from typing import Any, Dict

from helm_mcp_server.tools.discovery.chart_discovery import ChartDiscoveryTools
from helm_mcp_server.tools.installation.chart_management import ChartManagementTools
from helm_mcp_server.tools.kubernetes.cluster_ops import KubernetesTools
from helm_mcp_server.tools.monitoring.deployment_monitor import MonitoringTools
from helm_mcp_server.tools.registry import ToolRegistry


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all execution-layer tool modules."""
    registry = ToolRegistry(service_locator)

    registry.register_tool(ChartDiscoveryTools(service_locator))
    registry.register_tool(ChartManagementTools(service_locator))
    registry.register_tool(KubernetesTools(service_locator))
    registry.register_tool(MonitoringTools(service_locator))

    return registry
