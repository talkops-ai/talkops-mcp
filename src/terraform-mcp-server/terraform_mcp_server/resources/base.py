"""Base class for all Terraform MCP resources."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseResource(ABC):
    """Abstract base class for all Terraform MCP resources.
    
    Provides dependency injection via service_locator and enforces
    the register() contract for MCP resource registration.
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize resource with service locator.
        
        Args:
            service_locator: Dependency injection container with
                config, server_config, neo4j_graph, etc.
        """
        self.config = service_locator.get('config')
        self.server_config = service_locator.get('server_config')
        self.neo4j_graph = service_locator.get('neo4j_graph')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register resource(s) with the FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass
