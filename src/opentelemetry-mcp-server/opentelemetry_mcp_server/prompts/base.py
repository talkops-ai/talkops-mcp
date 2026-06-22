"""Base class for all prompts."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService


class BasePrompt(ABC):
    """Abstract base class for all prompts."""

    kubernetes_service: KubernetesService

    def __init__(self, service_locator: Dict[str, Any]):
        self.kubernetes_service = service_locator.get("kubernetes_service")  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
