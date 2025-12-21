"""Tools module initialization."""

from typing import Dict, Any
from helm_mcp_server.tools.registry import ToolRegistry
from helm_mcp_server.tools.discovery.chart_discovery import ChartDiscoveryTools
from helm_mcp_server.tools.installation.chart_management import ChartManagementTools
from helm_mcp_server.tools.validation.chart_validation import ValidationTools
from helm_mcp_server.tools.kubernetes.cluster_ops import KubernetesTools
from helm_mcp_server.tools.monitoring.deployment_monitor import MonitoringTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules.
    
    Args:
        service_locator: Dictionary of services
    
    Returns:
        Tool registry with all tools registered
    """
    registry = ToolRegistry(service_locator)
    
    # Register tool groups
    registry.register_tool(ChartDiscoveryTools(service_locator))
    registry.register_tool(ChartManagementTools(service_locator))
    registry.register_tool(ValidationTools(service_locator))
    registry.register_tool(KubernetesTools(service_locator))
    registry.register_tool(MonitoringTools(service_locator))
    
    return registry

