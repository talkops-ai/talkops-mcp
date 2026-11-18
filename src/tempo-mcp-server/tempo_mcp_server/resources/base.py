"""Base class for all dynamic Tempo MCP resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from tempo_mcp_server.config import ServerConfig
from tempo_mcp_server.services.kubernetes_service import KubernetesService
from tempo_mcp_server.services.tempo_service import TempoService


class BaseResource(ABC):
    """Abstract base class for all resources."""

    tempo_service: TempoService
    kubernetes_service: KubernetesService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        tempo_service = service_locator.get("tempo_service")
        if tempo_service is None:
            raise RuntimeError(
                "tempo_service not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.tempo_service = tempo_service

        config = service_locator.get("config")
        if config is None:
            raise RuntimeError(
                "config not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.config = config

        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        pass
