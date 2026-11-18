"""Server bootstrap for Alertmanager MCP."""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from alertmanager_mcp_server.config import Config, ServerConfig
from alertmanager_mcp_server.resources import initialize_resources
from alertmanager_mcp_server.server.core import create_mcp_server
from alertmanager_mcp_server.server.middleware import setup_middleware
from alertmanager_mcp_server.services import AlertmanagerService
from alertmanager_mcp_server.tools import initialize_tools


class ServerBootstrap:
    @staticmethod
    def initialize(
        config: Optional[ServerConfig] = None,
    ) -> tuple[FastMCP, ServerConfig, AlertmanagerService]:
        resolved_config = config if config is not None else Config.from_env()
        service = AlertmanagerService(resolved_config)
        mcp = create_mcp_server(resolved_config, service=service)
        setup_middleware(mcp, resolved_config)
        service_locator = {
            "alertmanager_service": service,
            "config": resolved_config,
        }
        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)
        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)
        return mcp, resolved_config, service
