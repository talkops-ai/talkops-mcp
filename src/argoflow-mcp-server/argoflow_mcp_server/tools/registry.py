"""Tool registry for managing all tools."""

from typing import Dict, Any, List
from argoflow_mcp_server.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing tools.
    
    Encapsulates tool registration and lifecycle management.
    Maintains a collection of all tools and provides methods to
    register them with the FastMCP instance.
    
    The registry pattern allows for:
    - Centralized tool management
    - Easy addition/removal of tools
    - Bulk registration with MCP instance
    - Tool discovery and introspection
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize registry.
        
        Args:
            service_locator: Dictionary of services that will be injected
                into each tool during instantiation. Contains:
                - argo_service: ArgoRollouts service
                - traefik_service: Traefik service
                - k8s_service: Kubernetes service
                - validation_service: Validation service
                - config: ServerConfig instance
        """
        self.service_locator = service_locator
        self.tools: List[BaseTool] = []
    
    def register_tool(self, tool: BaseTool) -> None:
        """Register a single tool with the registry.
        
        Adds the tool to the internal collection for later registration
        with the FastMCP instance.
        
        Args:
            tool: Tool instance that inherits from BaseTool
        
        Example:
            registry = ToolRegistry(service_locator)
            registry.register_tool(CreateRolloutTool(service_locator))
            registry.register_tool(PromoteRolloutTool(service_locator))
        """
        self.tools.append(tool)
    
    def register_all_tools(self, mcp_instance) -> None:
        """Register all tools with FastMCP instance.
        
        Iterates through all registered tools and calls their register()
        method to register them with the MCP server instance.
        
        Args:
            mcp_instance: FastMCP server instance
        
        Example:
            mcp = FastMCP("argoflow-mcp-server")
            registry.register_all_tools(mcp)
        """
        for tool in self.tools:
            tool.register(mcp_instance)
    
    def get_tools_count(self) -> int:
        """Get the number of registered tools.
        
        Returns:
            int: Number of tools in the registry
        """
        return len(self.tools)
    
    def get_tools(self) -> List[BaseTool]:
        """Get all registered tools.
        
        Returns:
            List[BaseTool]: List of all registered tool instances
        """
        return self.tools.copy()


