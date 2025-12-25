"""Server initialization and bootstrap."""

from argocd_mcp_server.config import ServerConfig, Config
from argocd_mcp_server.server.core import create_mcp_server
from argocd_mcp_server.services.argocd_service import ArgoCDService
from argocd_mcp_server.tools import initialize_tools
from argocd_mcp_server.resources import initialize_resources
from argocd_mcp_server.prompts import initialize_prompts


class ServerBootstrap:
    """Bootstrap the MCP server with all components."""
    
    @staticmethod
    def initialize() -> tuple:
        """Initialize server and all components.
        
        Returns:
            Tuple of (mcp_instance, config)
        """
        # 1. Load configuration
        config = Config.from_env()
        
        # 2. Create FastMCP instance
        mcp = create_mcp_server(config)
        
        # 3. Create service locator (dependency injection)
        service_locator = {
            'argocd_service': ArgoCDService(config),
            'config': config,  # Pass config for allow_write and other settings
        }
        
        # 4. Initialize and register tools
        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)
        
        # 5. Initialize and register resources
        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)
        
        # 6. Initialize and register prompts
        prompt_registry = initialize_prompts(service_locator)
        prompt_registry.register_all_prompts(mcp)
        
        return mcp, config
