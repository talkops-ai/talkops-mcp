"""Server bootstrap for Alertmanager MCP."""
from alertmanager_mcp_server.config import Config
from alertmanager_mcp_server.server.core import create_mcp_server
from alertmanager_mcp_server.server.middleware import setup_middleware
from alertmanager_mcp_server.services import AlertmanagerService
from alertmanager_mcp_server.tools import initialize_tools
from alertmanager_mcp_server.resources import initialize_resources
from alertmanager_mcp_server.prompts import initialize_prompts


class ServerBootstrap:
    @staticmethod
    def initialize() -> tuple:
        config = Config.from_env()
        mcp = create_mcp_server(config)
        setup_middleware(mcp, config)
        service = AlertmanagerService(config)
        service_locator = {
            'alertmanager_service': service,
            'config': config,
        }
        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)
        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)
        prompt_registry = initialize_prompts(service_locator)
        prompt_registry.register_all_prompts(mcp)
        return mcp, config, service
