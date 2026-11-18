"""Application configuration management for Kargo MCP Server.

Provides configuration for the Kargo MCP server, including
Kargo API settings, write-access gates, toolset filtering, and CLI/env parsing.
"""

import argparse
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence

VALID_TOOLSETS = frozenset({
    "all",
    "readonly",
    "pipeline",
    "promotion",
    "verification",
    "credentials",
    "rbac",
    "diagnostics",
})


class AuthMode(str, Enum):
    """Kargo API authentication mode."""

    ADMIN = "admin"              # Server logs in as Kargo admin, obtains JWT
    STATIC = "static"            # Server uses a pre-configured bearer token
    PASSTHROUGH = "passthrough"  # Forward caller token from MCP client


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
class KargoConfig:
    """Kargo API connection configuration."""

    base_url: str = "http://localhost:8080"
    verify_ssl: bool = True
    auth_mode: AuthMode = AuthMode.ADMIN
    admin_password: Optional[str] = None
    static_bearer_token: Optional[str] = None
    timeout: int = 30
    # Server-managed credential sources (never passed through LLM conversation)
    repo_username: Optional[str] = None
    repo_password: Optional[str] = None
    credentials_file: Optional[str] = None


@dataclass
class ServerConfig:
    """Main MCP server configuration."""

    # Server identity
    name: str = "kargo-mcp-server"
    version: str = "0.2.0"
    description: str = "Kargo Continuous Promotion MCP Execution Server"

    # Transport settings (supports stdio and http / streamable-http)
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8766
    path: str = "/mcp"

    # Security & toolset gates (read-only by default)
    allow_write: bool = False
    toolsets: List[str] = field(default_factory=lambda: ["all"])

    # Server behavior
    debug: bool = False
    default_project: Optional[str] = None

    # Kargo API configuration
    kargo: KargoConfig = field(default_factory=KargoConfig)

    def __post_init__(self) -> None:
        if self.kargo is None:
            self.kargo = KargoConfig()
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
        if self.transport == "streamable-http":
            self.transport = "http"
        if "readonly" in self.toolsets:
            self.allow_write = False


class Config:
    """Configuration loader and CLI argument parser."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        auth_mode_str = os.getenv("KARGO_AUTH_MODE", "admin").strip().lower()
        static_token = os.getenv("KARGO_STATIC_BEARER_TOKEN") or os.getenv("KARGO_AUTH_TOKEN") or None
        if auth_mode_str == "bearer":
            auth_mode = AuthMode.STATIC if static_token else AuthMode.ADMIN
        else:
            try:
                auth_mode = AuthMode(auth_mode_str)
            except ValueError:
                auth_mode = AuthMode.ADMIN

        allow_write = _parse_bool_env(os.getenv("MCP_ALLOW_WRITE"), default=False)
        if _parse_bool_env(os.getenv("MCP_READ_ONLY"), default=False):
            allow_write = False

        toolsets = _parse_toolsets(os.getenv("MCP_TOOLSETS", "all"))
        if "readonly" in toolsets:
            allow_write = False

        raw_transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
        if raw_transport == "streamable-http":
            raw_transport = "http"

        base_url = (
            os.getenv("KARGO_BASE_URL")
            or os.getenv("KARGO_API_URL")
            or "http://localhost:8080"
        )
        default_project = (
            os.getenv("KARGO_PROJECT")
            or os.getenv("KARGO_DEFAULT_PROJECT")
            or os.getenv("MCP_PROJECT")
            or None
        )

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "kargo-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", "0.2.0"),
            transport=raw_transport,
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8766")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allow_write=allow_write,
            toolsets=toolsets,
            debug=_parse_bool_env(os.getenv("MCP_DEBUG"), default=False),
            default_project=default_project,
            kargo=KargoConfig(
                base_url=base_url,
                verify_ssl=_parse_bool_env(os.getenv("KARGO_VERIFY_SSL"), default=True),
                auth_mode=auth_mode,
                admin_password=os.getenv("KARGO_ADMIN_PASSWORD"),
                static_bearer_token=static_token,
                timeout=int(os.getenv("KARGO_TIMEOUT", "30")),
                repo_username=os.getenv("KARGO_REPO_USERNAME"),
                repo_password=os.getenv("KARGO_REPO_PASSWORD"),
                credentials_file=os.getenv("KARGO_CREDENTIALS_FILE"),
            ),
        )

    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        """Create CLI argument parser."""
        parser = argparse.ArgumentParser(
            prog="kargo-mcp-server",
            description="Kargo Continuous Promotion MCP Execution Server",
        )
        parser.add_argument(
            "--transport",
            choices=["stdio", "http", "streamable-http"],
            default=None,
            help="MCP transport mode (default: env MCP_TRANSPORT or stdio)",
        )
        parser.add_argument("--host", default=None, help="HTTP server bind host")
        parser.add_argument("--port", type=int, default=None, help="HTTP server bind port")
        parser.add_argument("--path", default=None, help="HTTP server endpoint path")
        parser.add_argument(
            "--toolsets",
            default=None,
            help=(
                "Comma-separated toolsets to enable "
                f"({', '.join(sorted(VALID_TOOLSETS))})"
            ),
        )
        parser.add_argument(
            "--allow-write",
            action="store_true",
            default=False,
            help="Enable mutating and destructive Kargo tools",
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            default=False,
            help="Force read-only mode (overrides --allow-write and MCP_ALLOW_WRITE)",
        )
        parser.add_argument(
            "--kargo-url",
            default=None,
            help="Kargo API server base URL (overrides KARGO_BASE_URL)",
        )
        parser.add_argument(
            "--auth-mode",
            choices=["admin", "static", "passthrough"],
            default=None,
            help="Kargo authentication mode (overrides KARGO_AUTH_MODE)",
        )
        parser.add_argument(
            "--project",
            default=None,
            help="Optional default Kargo project name",
        )
        parser.add_argument(
            "--insecure-skip-tls-verify",
            action="store_true",
            default=False,
            help="Disable TLS certificate verification when connecting to Kargo API",
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
        cfg = cls.from_env()
        if argv is None:
            return cfg

        parser = cls.build_arg_parser()
        args = parser.parse_args(list(argv))

        if args.transport is not None:
            cfg.transport = "http" if args.transport == "streamable-http" else args.transport
        if args.host is not None:
            cfg.host = args.host
        if args.port is not None:
            cfg.port = args.port
        if args.path is not None:
            cfg.path = args.path
        if args.toolsets is not None:
            cfg.toolsets = _parse_toolsets(args.toolsets)
        if args.allow_write:
            cfg.allow_write = True
        if args.kargo_url is not None:
            cfg.kargo.base_url = args.kargo_url
        if args.auth_mode is not None:
            cfg.kargo.auth_mode = AuthMode(args.auth_mode)
        if args.project is not None:
            cfg.default_project = args.project
        if args.insecure_skip_tls_verify:
            cfg.kargo.verify_ssl = False
        if args.debug:
            cfg.debug = True

        # --read-only and 'readonly' toolset always win
        if args.read_only or "readonly" in cfg.toolsets:
            cfg.allow_write = False

        return cfg


def load_config(argv: Optional[Sequence[str]] = None) -> ServerConfig:
    """Convenience loader for ServerConfig."""
    return Config.from_cli_and_env(argv)
