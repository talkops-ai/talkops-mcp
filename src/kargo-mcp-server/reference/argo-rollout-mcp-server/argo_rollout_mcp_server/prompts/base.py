"""Base class for all prompts."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BasePrompt(ABC):
    """Abstract base class for all prompts."""
    
    def __init__(self, service_locator: Dict[str, Any]):
        self.argo_service = service_locator.get('argo_service')
        self.config = service_locator.get('config')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register prompts with FastMCP instance."""
        pass
