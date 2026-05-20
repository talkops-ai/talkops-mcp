"""Base class for all prompts."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from prometheus_mcp_server.services.prometheus_service import PrometheusService


class BasePrompt(ABC):
    """Abstract base class for all prompts."""

    prometheus_service: PrometheusService

    def __init__(self, service_locator: Dict[str, Any]):
        self.prometheus_service = service_locator.get('prometheus_service')  # type: ignore[assignment]

    @abstractmethod
    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        pass
