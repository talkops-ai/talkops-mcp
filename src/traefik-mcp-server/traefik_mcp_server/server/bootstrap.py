"""Server initialization and dependency-injected bootstrap."""

from typing import Any, Dict, Optional, Tuple

from traefik_mcp_server.config import Config, ServerConfig
from traefik_mcp_server.resources import initialize_resources
from traefik_mcp_server.server.core import create_mcp_server
from traefik_mcp_server.services.traefik_service import TraefikService
from traefik_mcp_server.tools import initialize_tools


class ServerBootstrap:
    """Bootstrap the Traefik MCP server with lazy Kubernetes client initialization."""

    @staticmethod
    def build(
        config: Optional[ServerConfig] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, ServerConfig]:
        """Build the FastMCP server instance with optional injected services for testing.

        Does not block or crash at startup if a Kubernetes cluster is unreachable.
        """
        cfg = config or Config.from_env()
        mcp = create_mcp_server(cfg)

        if services is not None and "traefik_service" in services:
            traefik_service = services["traefik_service"]
        else:
            traefik_service = TraefikService(cfg)
            traefik_service.enable_lazy_init()

        service_locator = {
            "traefik_service": traefik_service,
            "config": cfg,
        }

        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)

        return mcp, cfg

    @staticmethod
    def initialize(
        argv: Optional[list[str]] = None,
    ) -> Tuple[Any, ServerConfig]:
        """Initialize server from CLI arguments and environment variables."""
        cfg = Config.from_cli_and_env(argv)
        return ServerBootstrap.build(config=cfg)
