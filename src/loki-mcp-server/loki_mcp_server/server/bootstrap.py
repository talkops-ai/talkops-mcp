"""Server bootstrap — wires all components together.

This is the main entry point for initializing the MCP server.
It creates configurations, services, and registers all tools,
resources, and prompts using the dependency-injection service
locator pattern.

Logging is handled by FastMCP's StructuredLoggingMiddleware —
no custom logger is used.
"""

from typing import Any, Dict, Tuple

from fastmcp import FastMCP

from loki_mcp_server.config import Config, ServerConfig
from loki_mcp_server.server.core import create_mcp_server
from loki_mcp_server.services.loki_service import LokiService


class ServerBootstrap:
    """Bootstrap the MCP server with all dependencies wired."""

    @staticmethod
    def initialize() -> Tuple[FastMCP, ServerConfig, "LokiService"]:
        """Initialize the MCP server with all components registered.

        Steps:
        1. Load configuration from environment
        2. Create FastMCP instance with instructions and middleware
        3. Create LokiService (HTTP client)
        4. Build service_locator dependency injection dict
        5. Register all tools, resources, and prompts

        Returns:
            Tuple of (FastMCP instance, ServerConfig, LokiService).
        """
        # 1. Load configuration
        config = Config.from_env()

        # 2. Create FastMCP server (middleware + instructions)
        mcp = create_mcp_server(config)

        # 3. Create services
        loki_service = LokiService(config.loki, config.auth)

        # 4. Build service locator
        service_locator: Dict[str, Any] = {
            "loki_service": loki_service,
            "config": config,
        }

        # 5. Register tools
        from loki_mcp_server.tools import initialize_tools

        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all(mcp)

        # 6. Register resources
        from loki_mcp_server.resources import initialize_resources

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all(mcp)

        # 7. Register prompts
        from loki_mcp_server.prompts import initialize_prompts

        prompt_registry = initialize_prompts(service_locator)
        prompt_registry.register_all(mcp)

        print(
            f"Server '{config.name}' v{config.version} ready "
            f"(transport={config.transport})"
        )

        return mcp, config, loki_service
