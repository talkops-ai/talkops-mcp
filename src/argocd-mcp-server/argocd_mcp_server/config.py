"""Application configuration management."""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ArgoCDConfig:
    """ArgoCD configuration."""
    server_url: str = 'https://argocd-server.argocd.svc:443'
    auth_token: Optional[str] = None
    insecure: bool = False
    timeout: int = 300
    # If connection to multiple argocd instances is needed, we might need a mapping here.
    # For now, assuming one ArgoCD server manages multiple clusters.


@dataclass
class GitRepoConfig:
    """Git repository credentials for onboarding (HTTPS and SSH).

    Loaded from environment variables so secrets are not hardcoded.

    HTTPS (onboard_repository_https):
        GIT_USERNAME: Git username (can be empty for token-only auth).
        GIT_PASSWORD: Required for HTTPS; use a GitHub Personal Access Token (PAT).

    SSH (onboard_repository_ssh):
        SSH_PRIVATE_KEY_PATH: Path to SSH private key file (default: ~/.ssh/id_rsa).
    """
    username: str = ''
    password: Optional[str] = None
    ssh_private_key_path: str = '~/.ssh/id_rsa'

    @property
    def is_configured(self) -> bool:
        """True if HTTPS auth can be used (password is set)."""
        return bool(self.password)


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
    name: str = 'argocd-mcp-server'
    version: str = '0.1.0'
    transport: str = 'http'  # http (HTTP/SSE) or stdio
    host: str = '0.0.0.0'
    port: int = 8770  # HTTP/SSE server port
    path: str = '/mcp'  # SSE endpoint path
    allow_write: bool = False  # Enable write access for mutating operations
    # HTTP server timeout settings (in seconds)
    http_timeout: int = 300  # HTTP request timeout
    http_keepalive_timeout: int = 5  # HTTP keepalive timeout
    http_connect_timeout: int = 60  # HTTP connection timeout
    
    argocd: ArgoCDConfig = field(default_factory=ArgoCDConfig)
    git: GitRepoConfig = field(default_factory=GitRepoConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class Config:
    """Configuration loader."""
    
    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        config = ServerConfig(
            name=os.getenv('MCP_SERVER_NAME', 'argocd-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.1.0'),
            transport=os.getenv('MCP_TRANSPORT', 'http'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8770')),
            path=os.getenv('MCP_PATH', '/mcp'),
            allow_write=os.getenv('MCP_ALLOW_WRITE', 'true').lower() == 'true',
            http_timeout=int(os.getenv('MCP_HTTP_TIMEOUT', '300')),
            http_keepalive_timeout=int(os.getenv('MCP_HTTP_KEEPALIVE_TIMEOUT', '5')),
            http_connect_timeout=int(os.getenv('MCP_HTTP_CONNECT_TIMEOUT', '60')),
            argocd=ArgoCDConfig(
                server_url=os.getenv('ARGOCD_SERVER_URL', 'https://argocd-server.argocd.svc:443'),
                auth_token=os.getenv('ARGOCD_AUTH_TOKEN'),
                insecure=os.getenv('ARGOCD_INSECURE', 'false').lower() == 'true',
                timeout=int(os.getenv('ARGOCD_TIMEOUT', '300')),
            ),
            git=GitRepoConfig(
                username=os.getenv('GIT_USERNAME', ''),
                password=os.getenv('GIT_PASSWORD') or None,
                ssh_private_key_path=os.getenv('SSH_PRIVATE_KEY_PATH', '~/.ssh/id_rsa'),
            ),
            logging=LoggingConfig(
                level=os.getenv('MCP_LOG_LEVEL', 'INFO'),
                format=os.getenv('MCP_LOG_FORMAT', 'json'),
            ),
        )
        return config
