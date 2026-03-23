"""Server initialization and bootstrap."""

import asyncio
from traefik_mcp_server.config import ServerConfig, Config
from traefik_mcp_server.server.core import create_mcp_server
from traefik_mcp_server.services.traefik_service import TraefikService
from traefik_mcp_server.services.traefik_generator_service import TraefikGeneratorService
from traefik_mcp_server.services.nginx_migration_service import NginxMigrationService
from traefik_mcp_server.tools import initialize_tools
from traefik_mcp_server.resources import initialize_resources
from traefik_mcp_server.prompts import initialize_prompts


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
        
        # 3. Create services
        traefik_service = TraefikService(config)
        generator_service = TraefikGeneratorService(config=config)
        nginx_migration_service = NginxMigrationService(config=config)
        
        # 4. Initialize services asynchronously
        async def init_services():
            """Initialize all async services."""
            await traefik_service.initialize()
        
        # Run async initialization
        asyncio.run(init_services())
        
        # 5. Create service locator (dependency injection)
        service_locator = {
            'traefik_service': traefik_service,
            'generator_service': generator_service,  # Generator service
            'nginx_migration_service': nginx_migration_service,  # NGINX migration pipeline
            'config': config,  # Pass config for allow_write and other settings
        }
        
        # 6. Initialize and register tools
        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)
        
        # 7. Initialize and register resources
        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)
        
        # 8. Initialize and register prompts
        prompt_registry = initialize_prompts(service_locator)
        prompt_registry.register_all_prompts(mcp)
        
        return mcp, config
