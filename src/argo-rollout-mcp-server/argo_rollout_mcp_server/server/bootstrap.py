"""Server initialization and dependency-injected bootstrap."""

from typing import Any, Dict, Optional, Tuple

from argo_rollout_mcp_server.config import Config, ServerConfig
from argo_rollout_mcp_server.resources import initialize_resources
from argo_rollout_mcp_server.server.core import create_mcp_server
from argo_rollout_mcp_server.services.argo_rollouts_service import ArgoRolloutsService
from argo_rollout_mcp_server.services.generator_service import GeneratorService
from argo_rollout_mcp_server.tools import initialize_tools


class ServerBootstrap:
    """Bootstrap the Argo Rollouts MCP server with lazy Kubernetes client initialization."""

    @staticmethod
    def build(
        config: Optional[ServerConfig] = None,
        services: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, ServerConfig]:
        """Build the FastMCP server instance with optional injected services for testing.

        Does not block or crash at startup if a Kubernetes cluster is unreachable (fixes B10).
        """
        cfg = config or Config.from_env()
        mcp = create_mcp_server(cfg)

        if services is not None:
            generator_service = services.get("generator_service") or GeneratorService(config=cfg)
            argo_service = services.get("argo_service") or ArgoRolloutsService(
                cfg, generator_service=generator_service
            )
        else:
            generator_service = GeneratorService(config=cfg)
            argo_service = ArgoRolloutsService(cfg, generator_service=generator_service)
            argo_service.enable_lazy_init()

        service_locator = {
            "argo_service": argo_service,
            "generator_service": generator_service,
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
