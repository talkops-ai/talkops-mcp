"""Base class for all Terraform MCP tools."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    """Abstract base class for all Terraform MCP tools.
    
    Provides dependency injection via service_locator and enforces
    the register() contract for MCP tool registration.
    
    All tools have access to:
    - config: Domain Config (Neo4j, embeddings, LLM, etc.)
    - server_config: ServerConfig (transport, debug, etc.)
    - neo4j_graph: Neo4jGraph instance (may be None)
    """
    
    def __init__(self, service_locator: Dict[str, Any]):
        """Initialize tool with service locator.
        
        Args:
            service_locator: Dependency injection container.
        
        Raises:
            ValueError: If required 'config' key is missing.
        """
        config = service_locator.get('config')
        if config is None:
            raise ValueError(
                "Domain Config ('config') is required in service_locator"
            )
        
        self.config = config
        self.server_config = service_locator.get('server_config')
        self.neo4j_graph = service_locator.get('neo4j_graph')
    
    @abstractmethod
    def register(self, mcp_instance) -> None:
        """Register tool(s) with the FastMCP instance.
        
        Each subclass defines one or more @mcp_instance.tool() handlers.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        pass
