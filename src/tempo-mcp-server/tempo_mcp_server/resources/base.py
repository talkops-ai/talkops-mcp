"""Base class for all resources."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.config import ServerConfig


class BaseResource(ABC):
    """Abstract base class for all resources."""

    tempo_service: TempoService
    config: ServerConfig

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize resource with service locator.

        Raises:
            RuntimeError: If required services (tempo_service, config) are missing.
        """
        tempo_service = service_locator.get("tempo_service")
        if tempo_service is None:
            raise RuntimeError(
                "tempo_service not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.tempo_service: TempoService = tempo_service

        config = service_locator.get("config")
        if config is None:
            raise RuntimeError(
                "config not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.config: ServerConfig = config

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
