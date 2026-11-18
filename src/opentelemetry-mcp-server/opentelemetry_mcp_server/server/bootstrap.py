"""Server initialization and dependency-injected bootstrap."""

from typing import Any, Dict, Optional, Tuple

from opentelemetry_mcp_server.config import Config, ServerConfig
from opentelemetry_mcp_server.resources import initialize_resources
from opentelemetry_mcp_server.server.core import create_mcp_server
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService
from opentelemetry_mcp_server.tools import initialize_tools


class ServerBootstrap:
    """Bootstrap the OpenTelemetry MCP server with all execution components."""

    @staticmethod
    def build(
        config: Optional[ServerConfig] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, ServerConfig]:
        """Build the FastMCP server instance with optional injected services for testing."""
        cfg = config or Config.from_env()
        mcp = create_mcp_server(cfg)

        if services is not None:
            kubernetes_service = services.get(
                "kubernetes_service"
            ) or KubernetesService(cfg.kubernetes, cfg.otel_operator)
            collector_config_service = services.get(
                "collector_config_service"
            ) or CollectorConfigService()
        else:
            kubernetes_service = KubernetesService(
                cfg.kubernetes, cfg.otel_operator
            )
            collector_config_service = CollectorConfigService()

        service_locator = {
            "kubernetes_service": kubernetes_service,
            "collector_config_service": collector_config_service,
            "config": cfg,
        }

        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)

        return mcp, cfg

    @staticmethod
    def initialize(
        config: Optional[ServerConfig] = None,
        argv: Optional[list[str]] = None,
    ) -> Tuple[Any, ServerConfig]:
        """Initialize server and all components."""
        cfg = config or (
            Config.from_cli_and_env(argv)
            if argv is not None
            else Config.from_env()
        )
        return ServerBootstrap.build(config=cfg)
