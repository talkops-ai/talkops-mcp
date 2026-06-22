"""Tool registry for managing all Loki MCP tools."""

from typing import Any, Dict, List

from loki_mcp_server.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing tools.

    Encapsulates tool registration and lifecycle.
    """

    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool) -> None:
        """Add a tool group to the registry."""
        self.tools.append(tool)

    def register_all(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register all tools with the FastMCP instance."""
        for tool in self.tools:
            tool.register(mcp_instance)
