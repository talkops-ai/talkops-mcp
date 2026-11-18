"""Tool registry for managing all tools and toolset profiles."""

from typing import Any, Dict, List
from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing tools and filtering by active toolset profile."""

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize registry."""
        self.service_locator = service_locator
        self.config: Any = service_locator.get("config")
        self.tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool group instance."""
        self.tools.append(tool)

    def _is_toolset_enabled(self, toolset_name: str) -> bool:
        """Check whether a toolset group is enabled in config.toolsets."""
        if not self.config or not self.config.toolsets:
            return True
        configured = {t.lower() for t in self.config.toolsets}
        if "all" in configured or "readonly" in configured:
            return True
        return toolset_name.lower() in configured

    def register_all_tools(self, mcp_instance: Any) -> None:
        """Register all enabled tool groups with FastMCP instance."""
        for tool in self.tools:
            if self._is_toolset_enabled(tool.toolset_name):
                tool.register(mcp_instance)
