"""Server initialization and dependency-injected bootstrap."""

from typing import Any, Dict, Optional, Sequence, Tuple

from tempo_mcp_server.config import Config, ServerConfig
from tempo_mcp_server.resources import initialize_resources
from tempo_mcp_server.server.core import create_mcp_server
from tempo_mcp_server.services.kubernetes_service import KubernetesService
from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.tools import initialize_tools


class ServerBootstrap:
    """Bootstrap the Tempo MCP server with tools and dynamic resources (zero prompts)."""

    @staticmethod
    def build(
        config: Optional[ServerConfig] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, ServerConfig, TempoService]:
        """Build the FastMCP server instance with optional injected services for testing."""
        cfg = config or Config.from_env()
        mcp = create_mcp_server(cfg)

        if services is not None and "tempo_service" in services:
            tempo_service = services["tempo_service"]
        else:
            tempo_service = TempoService(cfg)

        if services is not None and "kubernetes_service" in services:
            kubernetes_service = services["kubernetes_service"]
        else:
            kubernetes_service = KubernetesService(
                cfg.kubernetes,
                operator_config=cfg.tempo_operator,
            )

        service_locator = {
            "tempo_service": tempo_service,
            "kubernetes_service": kubernetes_service,
            "config": cfg,
        }

        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)

        return mcp, cfg, tempo_service

    @staticmethod
    def initialize(
        argv: Optional[Sequence[str]] = None,
    ) -> Tuple[Any, ServerConfig, TempoService]:
        """Initialize server from CLI arguments and environment variables."""
        cfg = Config.from_cli_and_env(argv) if argv is not None else Config.from_env()
        return ServerBootstrap.build(config=cfg)
