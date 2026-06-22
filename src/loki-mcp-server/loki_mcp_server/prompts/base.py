"""Base class for all Loki MCP prompts."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from loki_mcp_server.config import ServerConfig


class BasePrompt(ABC):
    """Abstract base class for all Loki MCP prompts."""

    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        self.config = service_locator.get("config")  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
