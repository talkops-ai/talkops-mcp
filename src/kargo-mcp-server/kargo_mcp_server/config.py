"""Application configuration management."""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AuthMode(str, Enum):
    """Kargo API authentication mode."""
    ADMIN = "admin"             # Server logs in as Kargo admin, obtains JWT
    STATIC = "static"           # Server uses a pre-configured bearer token
    PASSTHROUGH = "passthrough"  # Forward caller token from MCP client


@dataclass
class KargoConfig:
    """Kargo API connection configuration."""
    base_url: str = "http://localhost:8080"
    verify_ssl: bool = True
    auth_mode: AuthMode = AuthMode.ADMIN
    admin_password: Optional[str] = None
    static_bearer_token: Optional[str] = None
    timeout: int = 30
    # Default repository credentials (sourced from env, never from agent)
    repo_username: Optional[str] = None
    repo_password: Optional[str] = None


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
    name: str = 'kargo-mcp-server'
    version: str = '0.1.0'
    transport: str = 'http'
    host: str = '0.0.0.0'
    port: int = 8766
    path: str = '/mcp'
    allow_write: bool = True  # Enable write access for mutating operations
    # HTTP server timeout settings (in seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    kargo: KargoConfig = field(default_factory=KargoConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class Config:
    """Configuration loader."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        auth_mode_str = os.getenv('KARGO_AUTH_MODE', 'admin').lower()
        try:
            auth_mode = AuthMode(auth_mode_str)
        except ValueError:
            auth_mode = AuthMode.ADMIN

        return ServerConfig(
            name=os.getenv('MCP_SERVER_NAME', 'kargo-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.1.0'),
            transport=os.getenv('MCP_TRANSPORT', 'http'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8766')),
            path=os.getenv('MCP_PATH', '/mcp'),
            allow_write=os.getenv('MCP_ALLOW_WRITE', 'true').lower() == 'true',
            http_timeout=int(os.getenv('MCP_HTTP_TIMEOUT', '300')),
            http_keepalive_timeout=int(os.getenv('MCP_HTTP_KEEPALIVE_TIMEOUT', '5')),
            http_connect_timeout=int(os.getenv('MCP_HTTP_CONNECT_TIMEOUT', '60')),
            kargo=KargoConfig(
                base_url=os.getenv('KARGO_BASE_URL', 'http://localhost:8080'),
                verify_ssl=os.getenv('KARGO_VERIFY_SSL', 'true').lower() == 'true',
                auth_mode=auth_mode,
                admin_password=os.getenv('KARGO_ADMIN_PASSWORD'),
                static_bearer_token=os.getenv('KARGO_STATIC_BEARER_TOKEN'),
                timeout=int(os.getenv('KARGO_TIMEOUT', '30')),
                repo_username=os.getenv('KARGO_REPO_USERNAME'),
                repo_password=os.getenv('KARGO_REPO_PASSWORD'),
            ),
            logging=LoggingConfig(
                level=os.getenv('MCP_LOG_LEVEL', 'INFO'),
                format=os.getenv('MCP_LOG_FORMAT', 'json'),
            ),
        )
