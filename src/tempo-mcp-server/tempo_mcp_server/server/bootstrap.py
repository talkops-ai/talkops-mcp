"""Server initialization and bootstrap."""

from tempo_mcp_server.config import Config
from tempo_mcp_server.server.core import create_mcp_server
from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.services.kubernetes_service import KubernetesService
from tempo_mcp_server.tools import initialize_tools
from tempo_mcp_server.resources import initialize_resources
from tempo_mcp_server.prompts import initialize_prompts


class ServerBootstrap:
    """Bootstrap the MCP server with all components."""

    @staticmethod
    def initialize() -> tuple:
        """Initialize server and all components.

        Returns:
            Tuple of (mcp_instance, config, tempo_service)
        """
        # 1. Load configuration
        config = Config.from_env()

        # 2. Create FastMCP instance
        mcp = create_mcp_server(config)

        # 3. Create service locator (dependency injection)
        tempo_service = TempoService(config)
        service_locator = {
            "tempo_service": tempo_service,
            "kubernetes_service": KubernetesService(
                config.kubernetes,
                operator_config=config.tempo_operator,
            ),
            "config": config,
        }

        # 4. Initialize and register tools
        tool_registry = initialize_tools(service_locator)
        tool_registry.register_all_tools(mcp)

        # 5. Initialize and register resources
        resource_registry = initialize_resources(service_locator)
        resource_registry.register_all_resources(mcp)

        # 6. Initialize and register prompts
        prompt_registry = initialize_prompts(service_locator)
        prompt_registry.register_all_prompts(mcp)

        return mcp, config, tempo_service
