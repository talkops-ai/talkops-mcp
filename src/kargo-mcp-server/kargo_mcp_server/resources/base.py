"""Base class for all Kargo MCP resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from kargo_mcp_server.config import ServerConfig
from kargo_mcp_server.services.kargo_service import KargoService


class BaseResource(ABC):
    """Abstract base class for all MCP resources."""

    kargo_service: KargoService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        self.kargo_service = service_locator.get("kargo_service")  # type: ignore[assignment]
        self.config = service_locator.get("config") or ServerConfig()

    @abstractmethod
    def register(self, mcp_instance: Any) -> None:
        pass
