"""Tool registry for managing all tools."""

from typing import Any, Dict, List

from opentelemetry_mcp_server.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing tools.

    Encapsulates tool registration and lifecycle.
    """

    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool) -> None:
        self.tools.append(tool)

    def register_all_tools(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        for tool in self.tools:
            tool.register(mcp_instance)
