"""Base class for all Loki MCP resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from loki_mcp_server.config import ServerConfig
from loki_mcp_server.services.loki_service import LokiService


class BaseResource(ABC):
    """Abstract base class for all Loki MCP resources."""

    loki_service: LokiService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        self.loki_service = service_locator.get("loki_service")  # type: ignore[assignment]
        self.config = service_locator.get("config")  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
