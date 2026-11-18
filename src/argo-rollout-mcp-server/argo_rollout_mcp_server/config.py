"""Application configuration management for Argo Rollout MCP Server.

Provides configuration for the Argo Rollout MCP server, including
Kubernetes settings, write-access gates, toolset filtering, and CLI/env parsing.
"""

import argparse
import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

VALID_TOOLSETS = frozenset({
    "all",
    "readonly",
    "rollouts",
    "migration",
    "analysis",
    "diagnostics",
})


def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_toolsets(raw: Optional[str]) -> List[str]:
    if not raw:
        return ["all"]
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not items:
        return ["all"]
    invalid = [t for t in items if t not in VALID_TOOLSETS]
    if invalid:
        raise ValueError(
            f"Unknown toolset(s): {', '.join(invalid)}. "
            f"Valid toolsets are: {', '.join(sorted(VALID_TOOLSETS))}"
        )
    return items


@dataclass
class KubernetesConfig:
    """Kubernetes client configuration."""

    kubeconfig: Optional[str] = None
    context_name: Optional[str] = None
    in_cluster: bool = False


@dataclass
class ServerConfig:
    """Main MCP server configuration."""

    # Server identity
    name: str = "argo-rollout-mcp-server"
    version: str = "0.2.0"
    description: str = "Argo Rollouts Progressive Delivery MCP Execution Server"

    # Transport settings
    transport: str = "stdio"  # stdio or http (streamable-http)
    host: str = "0.0.0.0"
    port: int = 8768
    path: str = "/mcp"

    # Security & toolset gates
    allow_write: bool = False
    toolsets: List[str] = field(default_factory=lambda: ["all"])

    # Server behavior
    debug: bool = False
    namespace: Optional[str] = None  # Optional default namespace filter (None = all namespaces)

    # Prometheus (for metrics resources and canary metric comparison)
    prometheus_url: Optional[str] = "http://prometheus:9090"

    # Kubernetes configuration
    kubernetes: Optional[KubernetesConfig] = None

    def __post_init__(self) -> None:
        if self.kubernetes is None:
            self.kubernetes = KubernetesConfig()
        if isinstance(self.toolsets, str):
            self.toolsets = _parse_toolsets(self.toolsets)
        else:
            normalized = [t.strip().lower() for t in self.toolsets if t and t.strip()]
            if not normalized:
                normalized = ["all"]
            invalid = [t for t in normalized if t not in VALID_TOOLSETS]
            if invalid:
                raise ValueError(
                    f"Unknown toolset(s): {', '.join(invalid)}. "
                    f"Valid toolsets are: {', '.join(sorted(VALID_TOOLSETS))}"
                )
            self.toolsets = normalized
        if "readonly" in self.toolsets:
            self.allow_write = False


class Config:
    """Configuration loader and manager."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        raw_prom = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
        prometheus_url = raw_prom.strip() if raw_prom and raw_prom.strip() else None

        allow_write = _parse_bool_env(os.getenv("MCP_ALLOW_WRITE"), default=False)
        if _parse_bool_env(os.getenv("MCP_READ_ONLY"), default=False):
            allow_write = False

        toolsets = _parse_toolsets(os.getenv("MCP_TOOLSETS", "all"))
        if "readonly" in toolsets:
            allow_write = False

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "argo-rollout-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", "0.2.0"),
            transport=os.getenv("MCP_TRANSPORT", "stdio").strip().lower(),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8768")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allow_write=allow_write,
            toolsets=toolsets,
            debug=_parse_bool_env(os.getenv("MCP_DEBUG"), default=False),
            namespace=os.getenv("K8S_NAMESPACE") or os.getenv("MCP_NAMESPACE") or None,
            prometheus_url=prometheus_url,
            kubernetes=KubernetesConfig(
                kubeconfig=os.getenv("K8S_KUBECONFIG") or os.getenv("KUBECONFIG"),
                context_name=os.getenv("K8S_CONTEXT"),
                in_cluster=_parse_bool_env(os.getenv("K8S_IN_CLUSTER"), default=False),
            ),
        )

    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        """Create CLI argument parser."""
        parser = argparse.ArgumentParser(
            prog="argo-rollout-mcp-server",
            description="Argo Rollouts Progressive Delivery MCP Server",
        )
        parser.add_argument(
            "--transport",
            choices=["stdio", "http", "streamable-http"],
            default=None,
            help="MCP transport mode (default: env MCP_TRANSPORT or stdio)",
        )
        parser.add_argument("--host", default=None, help="HTTP server bind host")
        parser.add_argument("--port", type=int, default=None, help="HTTP server port")
        parser.add_argument("--path", default=None, help="HTTP endpoint path")
        parser.add_argument(
            "--toolsets",
            default=None,
            help="Comma-separated toolsets to enable: all,readonly,rollouts,migration,analysis,diagnostics",
        )
        parser.add_argument(
            "--allow-write",
            action="store_true",
            default=False,
            help="Enable mutating and destructive cluster tools",
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            default=False,
            help="Force read-only mode (overrides --allow-write and MCP_ALLOW_WRITE)",
        )
        parser.add_argument(
            "--prometheus-url",
            default=None,
            help="Prometheus server base URL",
        )
        parser.add_argument(
            "--kubeconfig",
            default=None,
            help="Path to kubeconfig file",
        )
        parser.add_argument(
            "--context",
            default=None,
            help="Kubernetes kubeconfig context name",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            default=False,
            help="Enable debug logging",
        )
        return parser

    @classmethod
    def from_cli_and_env(cls, argv: Optional[Sequence[str]] = None) -> ServerConfig:
        """Load configuration from environment variables and apply CLI overrides."""
        parser = cls.build_arg_parser()
        args = parser.parse_args(list(argv) if argv is not None else [])
        cfg = cls.from_env()

        if args.transport:
            cfg.transport = "http" if args.transport == "streamable-http" else args.transport
        if args.host:
            cfg.host = args.host
        if args.port is not None:
            cfg.port = args.port
        if args.path:
            cfg.path = args.path
        if args.toolsets is not None:
            cfg.toolsets = _parse_toolsets(args.toolsets)
        if args.allow_write:
            cfg.allow_write = True
        if args.read_only or "readonly" in cfg.toolsets:
            cfg.allow_write = False
        if args.prometheus_url is not None:
            cfg.prometheus_url = args.prometheus_url or None
        if args.kubeconfig is not None:
            cfg.kubernetes.kubeconfig = args.kubeconfig
        if args.context is not None:
            cfg.kubernetes.context_name = args.context
        if args.debug:
            cfg.debug = True

        return cfg

    @staticmethod
    def get_default() -> ServerConfig:
        """Get default configuration (no environment variables)."""
        return ServerConfig(kubernetes=KubernetesConfig())


def load_config(argv: Optional[Sequence[str]] = None) -> ServerConfig:
    """Load server configuration from environment and optional CLI args."""
    if argv is not None:
        return Config.from_cli_and_env(argv)
    return Config.from_env()
