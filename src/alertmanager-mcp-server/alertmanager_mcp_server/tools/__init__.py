"""Tools module for Alertmanager MCP server.

Organizes the 14 tools into 4 domain toolsets:
- `triage`: `am_summarize_oncall`, `am_list_alerts`, `am_list_alert_groups`
- `routing`: `am_check_notification_health`, `am_explain_routing`, `am_push_test_alert` (mutating)
- `silences`: `am_list_silences`, `am_preview_silence`, `am_create_silence` (mutating),
  `am_silence_alert` (mutating), `am_update_silence` (mutating), `am_expire_silence` (mutating)
- `governance`: `am_audit_alert_hygiene`, `am_audit_silences`
"""

from typing import Any, Dict, List

from alertmanager_mcp_server.tools.base import BaseTool
from alertmanager_mcp_server.tools.governance_tools import GovernanceTools
from alertmanager_mcp_server.tools.routing_tools import RoutingTools
from alertmanager_mcp_server.tools.silence_tools import SilenceTools
from alertmanager_mcp_server.tools.triage_tools import TriageTools


class ToolRegistry:
    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool) -> None:
        self.tools.append(tool)

    def register_all_tools(self, mcp_instance: Any) -> None:
        for tool in self.tools:
            tool.register(mcp_instance)


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    registry = ToolRegistry(service_locator)
    registry.register_tool(TriageTools(service_locator))
    registry.register_tool(RoutingTools(service_locator))
    registry.register_tool(SilenceTools(service_locator))
    registry.register_tool(GovernanceTools(service_locator))
    return registry
