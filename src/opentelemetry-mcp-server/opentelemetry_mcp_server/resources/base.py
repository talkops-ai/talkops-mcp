"""Base class for all resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from opentelemetry_mcp_server.config import ServerConfig
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService


class BaseResource(ABC):
    """Abstract base class for all resources."""

    kubernetes_service: KubernetesService
    collector_config_service: CollectorConfigService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]
        self.collector_config_service = service_locator.get("collector_config_service")  # type: ignore[assignment]
        self.config = service_locator.get("config") or ServerConfig()

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        pass
