"""Base class for all prompts."""

from abc import ABC, abstractmethod
from typing import Dict, Any

from kargo_mcp_server.services.kargo_service import KargoService


class BasePrompt(ABC):
    """Abstract base class for all prompts."""

    kargo_service: KargoService

    def __init__(self, service_locator: Dict[str, Any]):
        self.kargo_service = service_locator.get('kargo_service')  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
