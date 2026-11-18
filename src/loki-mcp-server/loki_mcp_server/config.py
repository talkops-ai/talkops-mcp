"""Application configuration management.

Loads all configuration from environment variables and CLI flags following the
12-Factor methodology. Uses frozen dataclasses for type-safe, immutable
configuration objects.
"""

import argparse
import os
import re
from dataclasses import dataclass, field, replace
from typing import List, Literal, Optional, Sequence, Tuple

VALID_TOOLSETS = frozenset(
    {
        "all",
        "readonly",
        "discovery",
        "query",
        "analysis",
        "diagnostics",
        "rules",
        "governance",
        "operator",
    }
)


def _strip_env(value: Optional[str]) -> Optional[str]:
    """Strip inline comments and surrounding whitespace from a .env value."""
    if value is None:
        return None
    cleaned = re.sub(r"\s*#.*$", "", value).strip()
    return cleaned if cleaned else None


def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    """Parse a boolean environment variable."""
    cleaned = _strip_env(value)
    if cleaned is None:
        return default
    return cleaned.lower() in ("1", "true", "yes", "on")


def _parse_toolsets(raw: Optional[str] | Sequence[str]) -> Tuple[str, ...]:
    """Parse and validate toolset selection into an immutable tuple."""
    if raw is None:
        return ("all",)
    if isinstance(raw, str):
        cleaned = _strip_env(raw)
        if not cleaned:
            return ("all",)
        items = [item.strip().lower() for item in cleaned.split(",") if item.strip()]
    else:
        items = [str(item).strip().lower() for item in raw if str(item).strip()]
    if not items:
        return ("all",)
    invalid = [t for t in items if t not in VALID_TOOLSETS]
    if invalid:
        raise ValueError(
            f"Invalid toolset(s): {', '.join(invalid)}. "
            f"Valid toolsets are: {', '.join(sorted(VALID_TOOLSETS))}"
        )
    return tuple(items)


@dataclass(frozen=True)
class LokiConfig:
    """Loki HTTP API connection configuration."""

    base_url: str = "http://loki:3100"
    timeout: int = 30
    verify_ssl: bool = True


@dataclass(frozen=True)
class AuthConfig:
    """Authentication configuration for Loki.

    Supports Bearer token, Basic Auth, and multi-tenant
    X-Scope-OrgID headers.
    """

    auth_token: Optional[str] = None
    basic_auth_user: Optional[str] = None
    basic_auth_password: Optional[str] = None
    org_id: Optional[str] = None


@dataclass(frozen=True)
class GuardrailConfig:
    """Query safety guardrails.

    Enforces limits on query cost, time windows, result size,
    and label cardinality to prevent dangerous queries.
    """

    max_query_bytes: int = 5_000_000_000  # 5 GB
    max_time_window_hours: int = 336  # 14 days
    max_log_limit: int = 200  # max log lines per response
    max_series: int = 100  # max metric series (matrix) per response
    max_points_per_series: int = 200  # max data points per metric series
    high_cardinality_threshold: int = 10_000


@dataclass(frozen=True)
class KubernetesConfig:
    """Kubernetes cluster configuration for Loki Operator CRD inspection & apply."""

    kubeconfig: Optional[str] = None
    context_name: Optional[str] = None
    in_cluster: bool = False
    enabled: bool = False


@dataclass(frozen=True)
class LokiOperatorConfig:
    """Loki Operator CRD configuration."""

    crd_group: str = "loki.grafana.com"
    lokistack_version: str = "v1"
    rules_version: str = "v1beta1"


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: Literal["json", "text"] = "json"


@dataclass(frozen=True)
class ServerConfig:
    """Top-level MCP server configuration.

    Aggregates all sub-configurations and provides server transport and
    toolset/write-gate settings.
    """

    name: str = "loki-mcp-server"
    version: str = "0.2.1"
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8769
    path: str = "/mcp"

    # Security & toolset gates
    allow_write: bool = False
    toolsets: Tuple[str, ...] = ("all",)
    field_manager: str = "talkops-loki-mcp"
    debug: bool = False

    # Timeout settings (seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    # Response size limits (bytes)
    response_size_soft_limit: int = 40_000
    response_size_hard_limit: int = 200_000

    # Sub-configurations
    loki: LokiConfig = field(default_factory=LokiConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    loki_operator: LokiOperatorConfig = field(default_factory=LokiOperatorConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def __post_init__(self) -> None:
        normalized = _parse_toolsets(self.toolsets)
        object.__setattr__(self, "toolsets", normalized)
        if "readonly" in normalized:
            object.__setattr__(self, "allow_write", False)

    def should_register(self, toolset: str, is_write: bool = False) -> bool:
        """Check whether a tool in the given toolset should be registered."""
        active = set(self.toolsets or ("all",))
        if "readonly" in active and is_write:
            return False
        if is_write and not self.allow_write:
            return False
        if "all" in active or "readonly" in active:
            return True
        return toolset.lower() in active


class Config:
    """Configuration loader.

    Loads all settings from environment variables with sensible defaults
    and supports CLI argument overrides.
    """

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables.

        Returns:
            Fully populated ServerConfig instance.
        """
        if "PYTEST_CURRENT_TEST" not in os.environ:
            from dotenv import load_dotenv

            load_dotenv(override=False)

        allow_write = _parse_bool_env(os.getenv("MCP_ALLOW_WRITE"), default=False)
        if _parse_bool_env(os.getenv("MCP_READ_ONLY"), default=False) or _parse_bool_env(
            os.getenv("LOKI_READ_ONLY"), default=False
        ):
            allow_write = False

        raw_toolsets = (
            _strip_env(os.getenv("LOKI_TOOLSETS"))
            or _strip_env(os.getenv("MCP_TOOLSETS"))
            or "all"
        )
        toolsets = _parse_toolsets(raw_toolsets)
        if "readonly" in toolsets:
            allow_write = False

        return ServerConfig(
            name=_strip_env(os.getenv("MCP_SERVER_NAME")) or "loki-mcp-server",
            version=_strip_env(os.getenv("MCP_SERVER_VERSION")) or "0.2.1",
            transport=_strip_env(os.getenv("MCP_TRANSPORT")) or "stdio",
            host=_strip_env(os.getenv("MCP_HOST")) or "0.0.0.0",
            port=int(_strip_env(os.getenv("MCP_PORT")) or "8769"),
            path=_strip_env(os.getenv("MCP_PATH")) or "/mcp",
            allow_write=allow_write,
            toolsets=toolsets,
            field_manager=_strip_env(os.getenv("MCP_FIELD_MANAGER"))
            or "talkops-loki-mcp",
            debug=_parse_bool_env(os.getenv("MCP_DEBUG"), default=False),
            http_timeout=int(_strip_env(os.getenv("MCP_HTTP_TIMEOUT")) or "300"),
            http_keepalive_timeout=int(
                _strip_env(os.getenv("MCP_HTTP_KEEPALIVE_TIMEOUT")) or "5"
            ),
            http_connect_timeout=int(
                _strip_env(os.getenv("MCP_HTTP_CONNECT_TIMEOUT")) or "60"
            ),
            response_size_soft_limit=int(
                _strip_env(os.getenv("MCP_RESPONSE_SIZE_SOFT_LIMIT")) or "40000"
            ),
            response_size_hard_limit=int(
                _strip_env(os.getenv("MCP_RESPONSE_SIZE_HARD_LIMIT")) or "200000"
            ),
            loki=LokiConfig(
                base_url=_strip_env(os.getenv("LOKI_URL")) or "http://loki:3100",
                timeout=int(_strip_env(os.getenv("LOKI_TIMEOUT")) or "30"),
                verify_ssl=(_strip_env(os.getenv("LOKI_VERIFY_SSL")) or "true").lower()
                == "true",
            ),
            auth=AuthConfig(
                auth_token=_strip_env(os.getenv("LOKI_AUTH_TOKEN")),
                basic_auth_user=_strip_env(os.getenv("LOKI_BASIC_AUTH_USER")),
                basic_auth_password=_strip_env(os.getenv("LOKI_BASIC_AUTH_PASSWORD")),
                org_id=_strip_env(os.getenv("LOKI_ORG_ID")),
            ),
            guardrails=GuardrailConfig(
                max_query_bytes=int(
                    _strip_env(os.getenv("LOKI_MAX_QUERY_BYTES")) or "5000000000"
                ),
                max_time_window_hours=int(
                    _strip_env(os.getenv("LOKI_MAX_TIME_WINDOW_HOURS")) or "336"
                ),
                max_log_limit=int(
                    _strip_env(os.getenv("LOKI_MAX_LOG_LIMIT")) or "200"
                ),
                max_series=int(
                    _strip_env(os.getenv("LOKI_MAX_SERIES")) or "100"
                ),
                max_points_per_series=int(
                    _strip_env(os.getenv("LOKI_MAX_POINTS_PER_SERIES")) or "200"
                ),
                high_cardinality_threshold=int(
                    _strip_env(os.getenv("LOKI_HIGH_CARDINALITY_THRESHOLD")) or "10000"
                ),
            ),
            kubernetes=KubernetesConfig(
                kubeconfig=_strip_env(os.getenv("K8S_KUBECONFIG"))
                or _strip_env(os.getenv("KUBECONFIG")),
                context_name=_strip_env(os.getenv("K8S_CONTEXT")),
                in_cluster=_parse_bool_env(os.getenv("K8S_IN_CLUSTER"), default=False),
                enabled=_parse_bool_env(os.getenv("K8S_ENABLED"), default=False),
            ),
            loki_operator=LokiOperatorConfig(
                crd_group=_strip_env(os.getenv("LOKI_CRD_GROUP"))
                or "loki.grafana.com",
            ),
            logging=LoggingConfig(
                level=_strip_env(os.getenv("MCP_LOG_LEVEL")) or "INFO",
                format=_strip_env(os.getenv("MCP_LOG_FORMAT")) or "json",  # type: ignore[arg-type]
            ),
        )

    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        """Create CLI argument parser."""
        parser = argparse.ArgumentParser(
            prog="loki-mcp-server",
            description="Grafana Loki 3.x & Loki Operator MCP Execution Server",
        )
        parser.add_argument(
            "--transport",
            choices=["stdio", "http", "sse", "streamable-http"],
            default=None,
            help="MCP transport mode (default: stdio)",
        )
        parser.add_argument(
            "--host",
            default=None,
            help="HTTP bind host (default: 0.0.0.0)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=None,
            help="HTTP bind port (default: 8769)",
        )
        parser.add_argument(
            "--toolsets",
            default=None,
            help=(
                "Comma-separated toolsets: "
                "all,readonly,discovery,query,analysis,diagnostics,rules,governance,operator"
            ),
        )
        parser.add_argument(
            "--allow-write",
            action="store_true",
            default=False,
            help=(
                "Enable mutating tools (loki_upsert_rule_group, loki_delete_rule_group, "
                "loki_manage_delete_requests, loki_apply_operator_cr)"
            ),
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            default=False,
            help="Force read-only mode (overrides --allow-write and MCP_ALLOW_WRITE)",
        )
        parser.add_argument(
            "--loki-url",
            default=None,
            help="Primary Loki backend base URL override",
        )
        parser.add_argument(
            "--org-id",
            default=None,
            help="Default tenant ID (X-Scope-OrgID) override",
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
            "--k8s-enabled",
            action="store_true",
            default=False,
            help="Enable Kubernetes Loki Operator CRD discovery and management",
        )
        parser.add_argument(
            "--field-manager",
            default=None,
            help="Kubernetes Server-Side Apply fieldManager name (default: talkops-loki-mcp)",
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

        loki_cfg = cfg.loki
        auth_cfg = cfg.auth
        k8s_cfg = cfg.kubernetes

        if args.loki_url:
            loki_cfg = replace(loki_cfg, base_url=args.loki_url)
        if args.org_id:
            auth_cfg = replace(auth_cfg, org_id=args.org_id)
        if args.kubeconfig is not None:
            k8s_cfg = replace(k8s_cfg, kubeconfig=args.kubeconfig)
        if args.context is not None:
            k8s_cfg = replace(k8s_cfg, context_name=args.context)
        if args.k8s_enabled:
            k8s_cfg = replace(k8s_cfg, enabled=True)

        toolsets = (
            _parse_toolsets(args.toolsets) if args.toolsets is not None else cfg.toolsets
        )
        allow_write = True if args.allow_write else cfg.allow_write
        if args.read_only or "readonly" in toolsets:
            allow_write = False

        return replace(
            cfg,
            transport=args.transport or cfg.transport,
            host=args.host or cfg.host,
            port=args.port if args.port is not None else cfg.port,
            toolsets=toolsets,
            allow_write=allow_write,
            field_manager=args.field_manager or cfg.field_manager,
            debug=True if args.debug else cfg.debug,
            loki=loki_cfg,
            auth=auth_cfg,
            kubernetes=k8s_cfg,
        )
