"""Base class for all Loki MCP resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from loki_mcp_server.config import ServerConfig
from loki_mcp_server.services.kubernetes_service import KubernetesService
from loki_mcp_server.services.loki_service import LokiService


class BaseResource(ABC):
    """Abstract base class for all Loki MCP resources."""

    loki_service: LokiService
    kubernetes_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        self.loki_service = service_locator.get("loki_service")  # type: ignore[assignment]
        self.config = service_locator.get("config")  # type: ignore[assignment]
        k8s_svc: Optional[KubernetesService] = service_locator.get(
            "kubernetes_service"
        )
        if k8s_svc is None and self.config is not None:
            k8s_svc = KubernetesService(
                self.config.kubernetes,
                operator_config=self.config.loki_operator,
                field_manager=self.config.field_manager,
            )
        self.kubernetes_service = k8s_svc  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
