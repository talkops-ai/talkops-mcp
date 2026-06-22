"""Base class for all prompts."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from tempo_mcp_server.services.tempo_service import TempoService


class BasePrompt(ABC):
    """Abstract base class for all prompts."""

    tempo_service: TempoService

    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize prompt with service locator.

        Raises:
            RuntimeError: If tempo_service is missing from service_locator.
        """
        tempo_service = service_locator.get("tempo_service")
        if tempo_service is None:
            raise RuntimeError(
                "tempo_service not found in service_locator. "
                "Ensure bootstrap.py provides it."
            )
        self.tempo_service: TempoService = tempo_service

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
