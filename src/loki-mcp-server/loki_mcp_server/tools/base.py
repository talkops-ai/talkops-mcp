"""Base class for all Loki MCP tools."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from loki_mcp_server.config import ServerConfig
from loki_mcp_server.services.kubernetes_service import KubernetesService
from loki_mcp_server.services.loki_service import LokiService


class BaseTool(ABC):
    """Abstract base class for all Loki MCP tools.

    Subclasses implement specific tool logic while inheriting
    dependency injection via the service_locator pattern.
    """

    loki_service: LokiService
    kubernetes_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator."""
        loki_service = service_locator.get("loki_service")
        if loki_service is None:
            raise RuntimeError(
                "loki_service not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.loki_service: LokiService = loki_service

        config = service_locator.get("config")
        if config is None:
            raise RuntimeError(
                "config not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.config: ServerConfig = config

        k8s_svc: Optional[KubernetesService] = service_locator.get(
            "kubernetes_service"
        )
        if k8s_svc is None:
            k8s_svc = KubernetesService(
                self.config.kubernetes,
                operator_config=self.config.loki_operator,
                field_manager=self.config.field_manager,
            )
        self.kubernetes_service = k8s_svc

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register tool(s) with the FastMCP instance."""
        pass
