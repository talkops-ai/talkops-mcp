from typing import Any, Dict, TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from alertmanager_mcp_server.services import AlertmanagerService


class BaseResource(ABC):
    alertmanager_service: 'AlertmanagerService'

    def __init__(self, service_locator: Dict[str, Any]):
        self.alertmanager_service = service_locator['alertmanager_service']

    @abstractmethod
    def register(self, mcp_instance) -> None:
        pass
