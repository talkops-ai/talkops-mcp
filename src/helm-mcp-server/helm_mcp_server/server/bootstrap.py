"""Server initialization and bootstrap."""

from __future__ import annotations

from typing import Optional, Tuple

from fastmcp import FastMCP
from helm_mcp_server.config import Config, ServerConfig
from helm_mcp_server.resources import initialize_resources
from helm_mcp_server.server.core import create_mcp_server
from helm_mcp_server.services.helm_service import HelmService
from helm_mcp_server.services.kubernetes_service import KubernetesService
from helm_mcp_server.tools import initialize_tools


class ServerBootstrap:
    """Bootstrap the Helm MCP execution server with tools and resources."""

    @staticmethod
    def initialize(config: Optional[ServerConfig] = None) -> Tuple[FastMCP, ServerConfig]:
        """Initialize server, services, tools, and resources.

        Args:
            config: Optional explicit ServerConfig (loads from environment if omitted).

        Returns:
            Tuple of (mcp_instance, config)
        """
        resolved_config = config or Config.from_env()
        mcp = create_mcp_server(resolved_config)

        k8s_service = KubernetesService(resolved_config)
        helm_service = HelmService(resolved_config, k8s_service=k8s_service)

        service_locator = {
            "helm_service": helm_service,
            "k8s_service": k8s_service,
            "config": resolved_config,
        }

        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)

        return mcp, resolved_config
