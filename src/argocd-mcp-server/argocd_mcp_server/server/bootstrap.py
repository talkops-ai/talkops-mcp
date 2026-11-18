"""Server initialization and bootstrap."""

from typing import Optional, Tuple
from fastmcp import FastMCP

from argocd_mcp_server.config import Config, ServerConfig
from argocd_mcp_server.resources import initialize_resources
from argocd_mcp_server.server.core import create_mcp_server
from argocd_mcp_server.services import (
    ArgoCDClient,
    ArgoCDManagementService,
    ArgoCDService,
)
from argocd_mcp_server.tools import initialize_tools


class ServerBootstrap:
    """Bootstrap the MCP server with all execution and resource components."""

    @staticmethod
    def initialize(config: Optional[ServerConfig] = None) -> Tuple[FastMCP, ServerConfig]:
        """Initialize server and all components.

        Args:
            config: Optional pre-built ServerConfig (loads from environment if omitted).

        Returns:
            Tuple of (mcp_instance, config)
        """
        resolved_config = config or Config.from_env()
        mcp = create_mcp_server(resolved_config)

        shared_client = ArgoCDClient(resolved_config)
        argocd_service = ArgoCDService(resolved_config, client=shared_client)
        mgmt_service = ArgoCDManagementService(resolved_config, client=shared_client)

        service_locator = {
            "argocd_client": shared_client,
            "argocd_service": argocd_service,
            "mgmt_service": mgmt_service,
            "config": resolved_config,
        }

        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)

        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)

        return mcp, resolved_config
