"""MCP Server configuration for Terraform MCP Server.

Handles MCP runtime settings (transport, host, port, etc.) separately
from the domain-level Config class (Neo4j, embeddings, LLM, etc.).
"""

import os
from dataclasses import dataclass


@dataclass
class ServerConfig:
    """MCP server runtime configuration.
    
    Controls server identity, transport mode, and operational flags.
    Domain-level settings (Neo4j, embeddings, etc.) remain in Config.
    """
    # Server identity
    name: str = 'terraform-mcp-server'
    version: str = '0.1.0'
    description: str = 'Terraform Knowledge Graph MCP Server'
    
    # Transport settings
    transport: str = 'stdio'       # stdio or http
    host: str = '0.0.0.0'
    port: int = 8000
    path: str = '/mcp'
    
    # Server behavior
    debug: bool = False
    allow_dangerous_execution: bool = False  # Gate terraform apply/destroy


class MCPConfig:
    """Factory for loading MCP server configuration from environment."""
    
    @staticmethod
    def from_env() -> ServerConfig:
        """Load ServerConfig from MCP_* environment variables.
        
        Environment variables:
            MCP_TRANSPORT: 'stdio' (default) or 'http'
            MCP_HOST: bind address (default: 0.0.0.0)
            MCP_PORT: port number (default: 8000)
            MCP_PATH: HTTP endpoint path (default: /mcp)
            MCP_DEBUG: 'true'/'false' (default: false)
            MCP_ALLOW_DANGEROUS_EXECUTION: 'true'/'false' (default: false)
        
        Returns:
            Configured ServerConfig instance
        """
        return ServerConfig(
            name=os.getenv('MCP_SERVER_NAME', 'terraform-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.1.0'),
            transport=os.getenv('MCP_TRANSPORT', 'stdio'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8000')),
            path=os.getenv('MCP_PATH', '/mcp'),
            debug=os.getenv('MCP_DEBUG', 'false').lower() == 'true',
            allow_dangerous_execution=os.getenv(
                'MCP_ALLOW_DANGEROUS_EXECUTION', 'false'
            ).lower() == 'true',
        )
    
    @staticmethod
    def get_default() -> ServerConfig:
        """Get default configuration (no environment variables)."""
        return ServerConfig()
