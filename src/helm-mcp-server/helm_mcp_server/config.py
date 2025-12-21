"""Application configuration management."""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class HelmConfig:
    """Helm configuration."""
    timeout: int = 300
    repositories: list[str] = field(default_factory=lambda: ['bitnami'])
    max_concurrent_operations: int = 10


@dataclass
class KubernetesConfig:
    """Kubernetes configuration."""
    timeout: int = 30
    verify_ssl: bool = True
    connection_pool_size: int = 10
    kubeconfig: Optional[str] = None


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = 'INFO'
    format: str = 'json'
    file_path: str = './logs/mcp_server.log'
    max_bytes: int = 10485760  # 10MB


@dataclass
class ServerConfig:
    """MCP server configuration."""
    name: str = 'helm-mcp-server'
    version: str = '0.2.0'
    transport: str = 'http'  # http (HTTP/SSE) or stdio
    host: str = '0.0.0.0'
    port: int = 8765  # HTTP/SSE server port
    path: str = '/sse'  # SSE endpoint path
    allow_write: bool = False  # Enable write access for mutating operations
    # HTTP server timeout settings (in seconds)
    http_timeout: int = 300  # HTTP request timeout
    http_keepalive_timeout: int = 5  # HTTP keepalive timeout
    http_connect_timeout: int = 60  # HTTP connection timeout
    
    helm: HelmConfig = field(default_factory=HelmConfig)
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class Config:
    """Configuration loader."""
    
    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        return ServerConfig(
            name=os.getenv('MCP_SERVER_NAME', 'helm-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.2.0'),
            transport=os.getenv('MCP_TRANSPORT', 'http'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8765')),
            path=os.getenv('MCP_PATH', '/sse'),
            allow_write=os.getenv('MCP_ALLOW_WRITE', 'true').lower() == 'true',
            http_timeout=int(os.getenv('MCP_HTTP_TIMEOUT', '300')),
            http_keepalive_timeout=int(os.getenv('MCP_HTTP_KEEPALIVE_TIMEOUT', '5')),
            http_connect_timeout=int(os.getenv('MCP_HTTP_CONNECT_TIMEOUT', '60')),
            helm=HelmConfig(
                timeout=int(os.getenv('HELM_TIMEOUT', '300')),
            ),
            kubernetes=KubernetesConfig(
                timeout=int(os.getenv('K8S_TIMEOUT', '30')),
            ),
            logging=LoggingConfig(
                level=os.getenv('MCP_LOG_LEVEL', 'INFO'),
                format=os.getenv('MCP_LOG_FORMAT', 'json'),
            ),
        )

