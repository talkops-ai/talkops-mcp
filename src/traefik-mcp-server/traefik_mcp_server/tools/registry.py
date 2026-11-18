"""Tool registry for managing Traefik MCP toolsets."""

from typing import Any, Dict, List
from traefik_mcp_server.tools.base import BaseTool
from traefik_mcp_server.tools.diagnostics import DiagnosticTools
from traefik_mcp_server.tools.lifecycle import LifecycleTools
from traefik_mcp_server.tools.policies import PolicyTools
from traefik_mcp_server.tools.traffic import TrafficTools


class ToolRegistry:
    """Registry for managing and registering Traefik MCP toolsets."""

    def __init__(self, service_locator: Dict[str, Any]) -> None:
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool) -> None:
        self.tools.append(tool)

    def register_all_tools(self, mcp_instance: Any) -> None:
        for tool in self.tools:
            tool.register(mcp_instance)

    def get_tools_count(self) -> int:
        return len(self.tools)

    def get_tools(self) -> List[BaseTool]:
        return self.tools.copy()


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all toolset groups (traffic, policies, lifecycle, diagnostics)."""
    registry = ToolRegistry(service_locator)
    registry.register_tool(TrafficTools(service_locator))
    registry.register_tool(PolicyTools(service_locator))
    registry.register_tool(LifecycleTools(service_locator))
    registry.register_tool(DiagnosticTools(service_locator))
    return registry
