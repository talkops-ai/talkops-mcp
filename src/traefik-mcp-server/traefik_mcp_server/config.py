"""Application configuration management for Traefik MCP Server.

This module provides configuration for the Traefik MCP server,
including settings for Traefik, Kubernetes, and server behavior.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TraefikConfig:
    """Traefik specific configuration."""
    timeout: int = 120  # Operation timeout in seconds


@dataclass
class KubernetesConfig:
    """Kubernetes client configuration."""
    # Kubeconfig settings
    kubeconfig: Optional[str] = None  # Path to kubeconfig, None = auto-detect
    context_name: Optional[str] = None  # Specific context to use
    in_cluster: bool = False  # Force in-cluster config


@dataclass
class ServerConfig:
    """Main MCP server configuration.
    
    Root configuration object containing all subsystem configurations
    and server-level settings.
    """
    # Server identity
    name: str = 'traefik-mcp-server'
    version: str = '0.1.0'
    description: str = 'Traefik Traffic Management MCP Server'
    
    # Transport settings
    transport: str = 'http'  # http (HTTP/SSE) or stdio
    host: str = '0.0.0.0'
    port: int = 8769  # HTTP/SSE server port
    path: str = '/mcp'  # MCP endpoint path
    
    # Server behavior
    allow_write: bool = True  # Enable write access for mutating operations
    debug: bool = False
    
    # Traefik configuration
    traefik: TraefikConfig = field(default_factory=TraefikConfig)
    
    # Kubernetes configuration
    kubernetes: Optional[KubernetesConfig] = None

    def __post_init__(self):
        if self.kubernetes is None:
            self.kubernetes = KubernetesConfig()


class Config:
    """Configuration loader and manager."""
    
    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        return ServerConfig(
            # Server settings
            name=os.getenv('MCP_SERVER_NAME', 'traefik-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.1.0'),
            transport=os.getenv('MCP_TRANSPORT', 'http'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8769')),
            path=os.getenv('MCP_PATH', '/mcp'),
            allow_write=os.getenv('MCP_ALLOW_WRITE', 'true').lower() == 'true',
            debug=os.getenv('MCP_DEBUG', 'false').lower() == 'true',
            
            # Traefik configuration
            traefik=TraefikConfig(
                timeout=int(os.getenv('TRAEFIK_OPERATION_TIMEOUT', '120'))
            ),
            
            # Kubernetes configuration
            kubernetes=KubernetesConfig(
                kubeconfig=os.getenv('K8S_KUBECONFIG'),
                context_name=os.getenv('K8S_CONTEXT'),
                in_cluster=os.getenv('K8S_IN_CLUSTER', 'false').lower() == 'true',
            ),
        )
    
    @staticmethod
    def get_default() -> ServerConfig:
        """Get default configuration (no environment variables)."""
        return ServerConfig(kubernetes=KubernetesConfig())


def load_config() -> ServerConfig:
    """Load server configuration from environment."""
    return Config.from_env()
