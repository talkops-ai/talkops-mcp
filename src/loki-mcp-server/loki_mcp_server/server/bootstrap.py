"""Server bootstrap — wires all components together.

Initializes the Loki MCP execution server with dependency-injected
tools and dynamic resources (zero server-bound prompts; procedural
workflows reside in Agent Skills under `skills/`).
"""

from typing import Any, Dict, Optional, Sequence, Tuple

from fastmcp import FastMCP

from loki_mcp_server.config import Config, ServerConfig
from loki_mcp_server.server.core import create_mcp_server
from loki_mcp_server.services.kubernetes_service import KubernetesService
from loki_mcp_server.services.loki_service import LokiService


class ServerBootstrap:
    """Bootstrap the Loki MCP execution server with tools and dynamic resources."""

    @staticmethod
    def build(
        config: Optional[ServerConfig] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> Tuple[FastMCP, ServerConfig, LokiService]:
        """Build the FastMCP server instance with optional injected config/services."""
        cfg = config or Config.from_env()
        mcp = create_mcp_server(cfg)

        if services is not None and "loki_service" in services:
            loki_service: LokiService = services["loki_service"]
        else:
            loki_service = LokiService(cfg.loki, cfg.auth)

        if services is not None and "kubernetes_service" in services:
            kubernetes_service: KubernetesService = services["kubernetes_service"]
        else:
            kubernetes_service = KubernetesService(
                cfg.kubernetes,
                operator_config=cfg.loki_operator,
                field_manager=cfg.field_manager,
            )

        service_locator: Dict[str, Any] = {
            "loki_service": loki_service,
            "kubernetes_service": kubernetes_service,
            "config": cfg,
        }

        from loki_mcp_server.tools import initialize_tools

        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all(mcp)

        from loki_mcp_server.resources import initialize_resources

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all(mcp)

        return mcp, cfg, loki_service

    @staticmethod
    def initialize(
        argv: Optional[Sequence[str]] = None,
        config: Optional[ServerConfig] = None,
    ) -> Tuple[FastMCP, ServerConfig, LokiService]:
        """Initialize the MCP server from CLI arguments, explicit config, or environment."""
        if config is not None:
            return ServerBootstrap.build(config=config)
        cfg = Config.from_cli_and_env(argv) if argv is not None else Config.from_env()
        return ServerBootstrap.build(config=cfg)
