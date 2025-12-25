"""Tool registry for managing all tools."""

from typing import Dict, Any, List
from argocd_mcp_server.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing tools.
    
    Encapsulates tool registration and lifecycle.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize registry.
        
        Args:
            service_locator: Dictionary of services
        """
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool.
        
        Args:
            tool: Tool instance
        """
        self.tools.append(tool)
    
    def register_all_tools(self, mcp_instance) -> None:
        """Register all tools with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        for tool in self.tools:
            tool.register(mcp_instance)
