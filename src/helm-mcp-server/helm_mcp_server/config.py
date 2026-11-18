"""Application configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import List, Optional


def _default_package_version() -> str:
    """Resolve package version from installed metadata with fallback."""
    try:
        return pkg_version("talkops-helm-mcp-server")
    except PackageNotFoundError:
        return "0.5.0"


def _parse_toolsets(raw: str) -> List[str]:
    """Parse comma-separated toolset names into normalized list."""
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return items or ["all"]


@dataclass
class HelmConfig:
    """Helm CLI execution configuration."""

    timeout: int = 300
    max_concurrent_operations: int = 10


@dataclass
class KubernetesConfig:
    """Kubernetes API client configuration."""

    timeout: int = 30
    verify_ssl: bool = True
    connection_pool_size: int = 10
    kubeconfig: Optional[str] = None


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    file_path: str = "./logs/mcp_server.log"
    max_bytes: int = 10485760  # 10MB


@dataclass
class ServerConfig:
    """MCP server configuration."""

    name: str = "helm-mcp-server"
    version: str = field(default_factory=_default_package_version)
    transport: str = "stdio"  # 'stdio' or 'http' (streamable-http)
    host: str = "0.0.0.0"
    port: int = 8765
    path: str = "/mcp"
    allow_write: bool = False  # Read-only by default
    toolsets: List[str] = field(default_factory=lambda: ["all"])
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    helm: HelmConfig = field(default_factory=HelmConfig)
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @property
    def is_mutate_enabled(self) -> bool:
        """Return True if mutating tools should be exposed and permitted."""
        if not self.allow_write:
            return False
        normalized = {t.lower() for t in self.toolsets}
        if "readonly" in normalized or "read-only" in normalized:
            return False
        return bool(normalized & {"all", "mutate", "write"})

    @property
    def is_read_enabled(self) -> bool:
        """Return True if read-tier tools should be exposed."""
        normalized = {t.lower() for t in self.toolsets}
        return bool(normalized & {"all", "read", "readonly", "read-only"})


class Config:
    """Configuration loader from environment variables and CLI flags."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load server configuration from environment variables."""
        allow_write = os.getenv("MCP_ALLOW_WRITE", "false").strip().lower() == "true"
        toolsets = _parse_toolsets(os.getenv("MCP_TOOLSETS", "all"))
        if os.getenv("MCP_READ_ONLY", "").strip().lower() == "true":
            allow_write = False
            toolsets = ["read"]

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "helm-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", _default_package_version()),
            transport=os.getenv("MCP_TRANSPORT", "stdio").strip().lower(),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8765")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allow_write=allow_write,
            toolsets=toolsets,
            http_timeout=int(os.getenv("MCP_HTTP_TIMEOUT", "300")),
            http_keepalive_timeout=int(os.getenv("MCP_HTTP_KEEPALIVE_TIMEOUT", "5")),
            http_connect_timeout=int(os.getenv("MCP_HTTP_CONNECT_TIMEOUT", "60")),
            helm=HelmConfig(
                timeout=int(os.getenv("HELM_TIMEOUT", "300")),
            ),
            kubernetes=KubernetesConfig(
                timeout=int(os.getenv("K8S_TIMEOUT", "30")),
                kubeconfig=os.getenv("KUBECONFIG") or None,
            ),
            logging=LoggingConfig(
                level=os.getenv("MCP_LOG_LEVEL", "INFO"),
                format=os.getenv("MCP_LOG_FORMAT", "json"),
            ),
        )
