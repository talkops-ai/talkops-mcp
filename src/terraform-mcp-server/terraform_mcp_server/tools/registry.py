"""Tool registry for managing all Terraform MCP tools."""

from typing import Dict, Any, List
from terraform_mcp_server.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing tools.
    
    Centralizes tool registration and provides bulk registration
    with the FastMCP instance.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize registry with service locator.
        
        Args:
            service_locator: Dependency injection container with:
                - config: Domain Config instance
                - server_config: ServerConfig instance
                - neo4j_graph: Neo4jGraph instance (may be None)
        """
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool with the registry.
        
        Args:
            tool: Tool instance inheriting from BaseTool
        """
        self.tools.append(tool)
    
    def register_all_tools(self, mcp_instance) -> None:
        """Register all tools with the FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        for tool in self.tools:
            tool.register(mcp_instance)
    
    def get_tools_count(self) -> int:
        """Get number of registered tool categories."""
        return len(self.tools)
    
    def get_tools(self) -> List[BaseTool]:
        """Get all registered tool instances."""
        return self.tools.copy()
