"""Tools module for Alertmanager MCP server.

v4 refactor: DiscoveryTools removed — backend discovery is now handled
by resources (am://system/backends, am://system/backends/{backend_id}).

Active tool groups (6): AlertTools, SilenceTools, HelperTools, RoutingTools,
GovernanceTools, TriageTools — totaling 14 tools.
"""
from typing import Any, Dict, List
from alertmanager_mcp_server.tools.base import BaseTool


class ToolRegistry:
    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool) -> None:
        self.tools.append(tool)

    def register_all_tools(self, mcp_instance) -> None:
        for tool in self.tools:
            tool.register(mcp_instance)


# Import tool classes
from alertmanager_mcp_server.tools.alert_tools import AlertTools
from alertmanager_mcp_server.tools.silence_tools import SilenceTools
from alertmanager_mcp_server.tools.helper_tools import HelperTools
from alertmanager_mcp_server.tools.routing_tools import RoutingTools
from alertmanager_mcp_server.tools.governance_tools import GovernanceTools
from alertmanager_mcp_server.tools.triage_tools import TriageTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    registry = ToolRegistry(service_locator)
    registry.register_tool(AlertTools(service_locator))
    registry.register_tool(SilenceTools(service_locator))
    registry.register_tool(HelperTools(service_locator))
    registry.register_tool(RoutingTools(service_locator))
    registry.register_tool(GovernanceTools(service_locator))
    registry.register_tool(TriageTools(service_locator))
    return registry
