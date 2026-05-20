from typing import Any, Dict, TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from alertmanager_mcp_server.services import AlertmanagerService
    from alertmanager_mcp_server.config import ServerConfig


class BaseTool(ABC):
    alertmanager_service: 'AlertmanagerService'
    config: 'ServerConfig'

    def __init__(self, service_locator: Dict[str, Any]):
        self.alertmanager_service = service_locator['alertmanager_service']
        self.config = service_locator['config']

    @abstractmethod
    def register(self, mcp_instance) -> None:
        pass
