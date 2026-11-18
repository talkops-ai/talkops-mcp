"""Server initialization and bootstrap."""

from typing import Optional

from fastmcp import FastMCP

from prometheus_mcp_server.config import Config, ServerConfig
from prometheus_mcp_server.resources import initialize_resources
from prometheus_mcp_server.server.core import create_mcp_server
from prometheus_mcp_server.services.kubernetes_service import KubernetesService
from prometheus_mcp_server.services.prometheus_service import PrometheusService
from prometheus_mcp_server.tools import initialize_tools


class ServerBootstrap:
    """Bootstrap the MCP server with all components."""

    @staticmethod
    def initialize(
        config: Optional[ServerConfig] = None,
    ) -> tuple[FastMCP, ServerConfig]:
        """Initialize server and all components.

        Returns:
            Tuple of (mcp_instance, config)
        """
        if config is None:
            config = Config.from_env()

        mcp = create_mcp_server(config)

        # Initialize services
        prometheus_service = PrometheusService(config)
        kubernetes_service = (
            KubernetesService(config.kubernetes) if config.kubernetes.enabled else None
        )

        # Create service locator
        service_locator = {
            "prometheus_service": prometheus_service,
            "kubernetes_service": kubernetes_service,
            "config": config,
        }

        # Initialize and register tools and dynamic resources
        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)

        return mcp, config
