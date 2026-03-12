"""Tool registry for managing all tools."""

from typing import Dict, Any, List
from argo_rollout_mcp_server.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing tools."""
    
    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []
    
    def register_tool(self, tool: BaseTool) -> None:
        self.tools.append(tool)
    
    def register_all_tools(self, mcp_instance) -> None:
        for tool in self.tools:
            tool.register(mcp_instance)
    
    def get_tools_count(self) -> int:
        return len(self.tools)
    
    def get_tools(self) -> List[BaseTool]:
        return self.tools.copy()
