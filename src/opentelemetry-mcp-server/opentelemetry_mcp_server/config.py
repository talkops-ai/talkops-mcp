"""Application configuration management.

Loads all configuration from environment variables and optional CLI arguments
following the 12-Factor methodology. Uses frozen dataclasses for type-safe,
immutable configuration objects.
"""

import argparse
import os
from dataclasses import dataclass, field, replace
from typing import List, Literal, Optional, Sequence

VALID_TOOLSETS = frozenset({
    "all",
    "readonly",
    "discovery",
    "collector",
    "instrumentation",
    "pipeline",
    "diagnostics",
    "governance",
    "ui",
})


def _strip_env(name: str) -> Optional[str]:
    """Read an environment variable, returning None if unset or blank."""
    raw = os.getenv(name)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped if stripped else None


def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    """Parse a boolean environment variable string."""
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_toolsets(raw: Optional[str | Sequence[str]]) -> List[str]:
    """Parse and validate a comma-separated string or sequence of toolsets."""
    if not raw:
        return ["all"]
    if isinstance(raw, str):
        items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    else:
        items = [str(item).strip().lower() for item in raw if item and str(item).strip()]
    if not items:
        return ["all"]
    invalid = [t for t in items if t not in VALID_TOOLSETS]
    if invalid:
        raise ValueError(
            f"Unknown toolset(s): {', '.join(invalid)}. "
            f"Valid toolsets are: {', '.join(sorted(VALID_TOOLSETS))}"
        )
    return items


@dataclass(frozen=True)
class KubernetesConfig:
    """Kubernetes cluster configuration."""

    in_cluster: bool = False
    enabled: bool = True
    kubeconfig: Optional[str] = None
    context_name: Optional[str] = None


@dataclass(frozen=True)
class OtelOperatorConfig:
    """OpenTelemetry Operator CRD configuration.

    Controls which API group/version is used when interacting with
    OpenTelemetryCollector, Instrumentation, TargetAllocator, and OpAMPBridge
    custom resources.
    """

    crd_group: str = "opentelemetry.io"
    crd_api_version: str = "v1beta1"
    instrumentation_api_version: str = "v1alpha1"
    target_allocator_api_version: str = "v1alpha1"
    opamp_bridge_api_version: str = "v1alpha1"
    collector_plural: str = "opentelemetrycollectors"
    instrumentation_plural: str = "instrumentations"
    target_allocator_plural: str = "targetallocators"
    opamp_bridge_plural: str = "opampbridges"


@dataclass(frozen=True)
class TargetAllocatorConfig:
    """Target Allocator configuration."""

    service_discovery_enabled: bool = True
    default_port: int = 8080


@dataclass(frozen=True)
class PrometheusIntegrationConfig:
    """Prometheus integration configuration for cardinality queries."""

    base_url: Optional[str] = None
    timeout: int = 30
    verify_ssl: bool = True


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: Literal["json", "text"] = "json"
    file_path: str = "./logs/mcp_server.log"
    max_bytes: int = 10_485_760  # 10 MB


@dataclass(frozen=True)
class ServerConfig:
    """Top-level MCP server configuration.

    Aggregates all sub-configurations, write-access gates, toolset filters,
    and server transport settings.
    """

    name: str = "opentelemetry-mcp-server"
    version: str = "0.2.1"
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8768
    path: str = "/mcp"

    # Security & toolset gates
    allow_write: bool = False
    read_only: bool = False
    toolsets: List[str] = field(default_factory=lambda: ["all"])
    collector_version_default: str = "0.152.1"

    # Timeout settings (seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    # Sub-configurations
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    otel_operator: OtelOperatorConfig = field(default_factory=OtelOperatorConfig)
    target_allocator: TargetAllocatorConfig = field(
        default_factory=TargetAllocatorConfig
    )
    prometheus: PrometheusIntegrationConfig = field(
        default_factory=PrometheusIntegrationConfig
    )
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def __post_init__(self) -> None:
        normalized = _parse_toolsets(self.toolsets)
        object.__setattr__(self, "toolsets", normalized)
        if self.read_only or "readonly" in normalized:
            object.__setattr__(self, "allow_write", False)

    @property
    def write_enabled(self) -> bool:
        """Return True only when write operations are explicitly enabled."""
        return bool(
            self.allow_write
            and not self.read_only
            and "readonly" not in self.toolsets
        )


class Config:
    """Configuration loader.

    Loads all settings from environment variables and optional CLI arguments
    with sensible defaults.
    """

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables.

        Note: Does not call load_dotenv() so unit tests remain isolated from
        local .env files. CLI startup calls load_dotenv() explicitly in main().

        Returns:
            Fully populated ServerConfig instance.
        """
        allow_write = _parse_bool_env(os.getenv("MCP_ALLOW_WRITE"), default=False)
        read_only = _parse_bool_env(os.getenv("MCP_READ_ONLY"), default=False)
        if read_only:
            allow_write = False

        toolsets = _parse_toolsets(os.getenv("MCP_TOOLSETS", "all"))
        if "readonly" in toolsets:
            allow_write = False

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "opentelemetry-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", "0.2.1"),
            transport=os.getenv("MCP_TRANSPORT", "stdio").strip().lower(),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8768")),
            path=os.getenv("MCP_PATH", "/mcp"),
            allow_write=allow_write,
            read_only=read_only,
            toolsets=toolsets,
            collector_version_default=os.getenv(
                "OTEL_COLLECTOR_VERSION_DEFAULT", "0.152.1"
            ),
            http_timeout=int(os.getenv("MCP_HTTP_TIMEOUT", "300")),
            http_keepalive_timeout=int(
                os.getenv("MCP_HTTP_KEEPALIVE_TIMEOUT", "5")
            ),
            http_connect_timeout=int(
                os.getenv("MCP_HTTP_CONNECT_TIMEOUT", "60")
            ),
            kubernetes=KubernetesConfig(
                in_cluster=_parse_bool_env(
                    _strip_env("K8S_IN_CLUSTER"), default=False
                ),
                enabled=_parse_bool_env(_strip_env("K8S_ENABLED"), default=True),
                kubeconfig=_strip_env("K8S_KUBECONFIG")
                or _strip_env("KUBECONFIG")
                or None,
                context_name=_strip_env("K8S_CONTEXT")
                or _strip_env("KUBE_CONTEXT")
                or None,
            ),
            otel_operator=OtelOperatorConfig(
                crd_group=_strip_env("OTEL_CRD_GROUP") or "opentelemetry.io",
                crd_api_version=_strip_env("OTEL_CRD_API_VERSION") or "v1beta1",
                instrumentation_api_version=_strip_env(
                    "OTEL_INSTRUMENTATION_API_VERSION"
                ) or "v1alpha1",
                target_allocator_api_version=_strip_env(
                    "OTEL_TARGET_ALLOCATOR_API_VERSION"
                ) or "v1beta1",
                opamp_bridge_api_version=_strip_env(
                    "OTEL_OPAMP_BRIDGE_API_VERSION"
                ) or "v1alpha1",
                collector_plural=_strip_env("OTEL_COLLECTOR_PLURAL")
                or "opentelemetrycollectors",
                instrumentation_plural=_strip_env("OTEL_INSTRUMENTATION_PLURAL")
                or "instrumentations",
                target_allocator_plural=_strip_env(
                    "OTEL_TARGET_ALLOCATOR_PLURAL"
                ) or "targetallocators",
                opamp_bridge_plural=_strip_env("OTEL_OPAMP_BRIDGE_PLURAL")
                or "opampbridges",
            ),
            target_allocator=TargetAllocatorConfig(
                service_discovery_enabled=_parse_bool_env(
                    _strip_env("OTEL_TA_SERVICE_DISCOVERY"), default=True
                ),
                default_port=int(_strip_env("OTEL_TA_DEFAULT_PORT") or "8080"),
            ),
            prometheus=PrometheusIntegrationConfig(
                base_url=_strip_env("PROMETHEUS_BASE_URL")
                or _strip_env("PROMETHEUS_URL"),
                timeout=int(_strip_env("PROMETHEUS_TIMEOUT") or "30"),
                verify_ssl=_parse_bool_env(
                    _strip_env("PROMETHEUS_VERIFY_SSL"), default=True
                ),
            ),
            logging=LoggingConfig(
                level=os.getenv("MCP_LOG_LEVEL", "INFO"),
                format=os.getenv("MCP_LOG_FORMAT", "json"),  # type: ignore[arg-type]
            ),
        )

    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        """Create CLI argument parser."""
        parser = argparse.ArgumentParser(
            prog="opentelemetry-mcp-server",
            description="OpenTelemetry on Kubernetes MCP Execution Server",
        )
        parser.add_argument(
            "--transport",
            choices=["stdio", "http", "sse", "streamable-http"],
            default=None,
            help="MCP transport mode (default: env MCP_TRANSPORT or stdio)",
        )
        parser.add_argument("--host", default=None, help="HTTP server bind host")
        parser.add_argument(
            "--port", type=int, default=None, help="HTTP server port"
        )
        parser.add_argument(
            "--path", default=None, help="HTTP endpoint path"
        )
        parser.add_argument(
            "--toolsets",
            default=None,
            help=(
                "Comma-separated toolsets to enable: "
                "all,readonly,discovery,collector,instrumentation,pipeline,diagnostics,governance,ui"
            ),
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
            "--collector-version-default",
            default=None,
            help="Default OpenTelemetry Collector version tag (default: 0.152.1)",
        )
        return parser

    @classmethod
    def from_cli_and_env(cls, argv: Optional[Sequence[str]] = None) -> ServerConfig:
        """Load configuration from environment variables and apply CLI overrides."""
        parser = cls.build_arg_parser()
        args = parser.parse_args(list(argv) if argv is not None else [])
        cfg = cls.from_env()

        k8s_cfg = cfg.kubernetes
        if args.kubeconfig is not None:
            k8s_cfg = replace(k8s_cfg, kubeconfig=args.kubeconfig)
        if args.context is not None:
            k8s_cfg = replace(k8s_cfg, context_name=args.context)

        transport = args.transport if args.transport else cfg.transport
        toolsets = (
            _parse_toolsets(args.toolsets)
            if args.toolsets is not None
            else cfg.toolsets
        )
        allow_write = True if args.allow_write else cfg.allow_write
        read_only = True if args.read_only else cfg.read_only
        if read_only or "readonly" in toolsets:
            allow_write = False

        return replace(
            cfg,
            transport=transport,
            host=args.host if args.host is not None else cfg.host,
            port=args.port if args.port is not None else cfg.port,
            path=args.path if args.path is not None else cfg.path,
            toolsets=toolsets,
            allow_write=allow_write,
            read_only=read_only,
            collector_version_default=(
                args.collector_version_default
                if args.collector_version_default is not None
                else cfg.collector_version_default
            ),
            kubernetes=k8s_cfg,
        )
