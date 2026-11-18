"""Application configuration management for Traefik MCP Server.

Provides configuration for the Traefik MCP server, including Kubernetes settings,
write-access gates, toolset filtering, namespace/ownership guard settings,
Traefik runtime API settings, and CLI/env parsing.
"""

import argparse
import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

VALID_TOOLSETS = frozenset({
    "all",
    "readonly",
    "traffic",
    "policies",
    "diagnostics",
})


def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_csv_list(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or None


def _parse_toolsets(raw: Optional[str]) -> List[str]:
    if not raw:
        return ["all"]
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not items:
        return ["all"]
    invalid = [t for t in items if t not in VALID_TOOLSETS]
    if invalid:
        raise ValueError(
            f"Invalid toolset(s): {', '.join(invalid)}. "
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
    name: str = "traefik-mcp-server"
    version: str = "0.2.1"
    description: str = "Traefik v3 Traffic Management & Diagnostics MCP Execution Server"

    # Transport settings (local stdio only per D6)
    transport: str = "stdio"

    # Security & toolset gates
    allow_write: bool = False
    toolsets: List[str] = field(default_factory=lambda: ["all"])

    # Server behavior & namespace policies
    debug: bool = False
    namespace: Optional[str] = None  # Optional default namespace filter (None = all namespaces)
    traefik_namespace: str = "traefik"
    traefik_api_url: Optional[str] = None  # Optional override; defaults to K8s pods/proxy
    traefik_http_url: Optional[str] = None  # Optional local/LB HTTP entrypoint URL for live probes
    traefik_https_url: Optional[str] = None  # Optional local/LB HTTPS entrypoint URL for live probes
    allowed_namespaces: Optional[List[str]] = None
    protected_namespaces: List[str] = field(default_factory=lambda: ["kube-system", "traefik"])
    field_manager: str = "talkops-traefik-mcp"
    cert_expiry_warning_days: int = 21
    probe_allow_any_host: bool = False
    log_max_lines: int = 5000

    # Prometheus (for metrics resources and canary metric comparison)
    prometheus_url: Optional[str] = "http://prometheus:9090"

    # Kubernetes configuration
    kubernetes: Optional[KubernetesConfig] = None

    def __post_init__(self) -> None:
        if self.kubernetes is None:
            self.kubernetes = KubernetesConfig()
        if self.transport != "stdio":
            raise ValueError(
                f"Unsupported transport '{self.transport}'. "
                "Traefik MCP Server operates in local stdio mode only ('stdio')."
            )
        if isinstance(self.toolsets, str):
            self.toolsets = _parse_toolsets(self.toolsets)
        else:
            normalized = [t.strip().lower() for t in self.toolsets if t and t.strip()]
            if not normalized:
                normalized = ["all"]
            invalid = [t for t in normalized if t not in VALID_TOOLSETS]
            if invalid:
                raise ValueError(
                    f"Invalid toolset(s): {', '.join(invalid)}. "
                    f"Valid toolsets are: {', '.join(sorted(VALID_TOOLSETS))}"
                )
            self.toolsets = normalized
        if "readonly" in self.toolsets:
            self.allow_write = False
        if self.traefik_namespace and self.traefik_namespace not in self.protected_namespaces:
            self.protected_namespaces = list(dict.fromkeys([*self.protected_namespaces, self.traefik_namespace]))

    def should_register(self, toolset: str, is_write: bool = False) -> bool:
        """Check whether a tool in the given toolset should be registered under this config."""
        active = set(self.toolsets or ["all"])
        if "readonly" in active:
            return not is_write
        if is_write and not self.allow_write:
            return False
        if "all" in active:
            return True
        return toolset in active


class Config:
    """Configuration loader and manager."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        raw_prom = os.getenv("PROMETHEUS_URL") or os.getenv("PROMETHEUS_BASE_URL") or "http://prometheus:9090"
        prometheus_url = raw_prom.strip() if raw_prom and raw_prom.strip() else None

        allow_write = _parse_bool_env(os.getenv("MCP_ALLOW_WRITE"), default=False)
        if _parse_bool_env(os.getenv("MCP_READ_ONLY"), default=False):
            allow_write = False

        toolsets = _parse_toolsets(os.getenv("MCP_TOOLSETS", "all"))
        if "readonly" in toolsets:
            allow_write = False

        traefik_ns = os.getenv("TRAEFIK_NAMESPACE", "traefik").strip() or "traefik"
        protected_ns = _parse_csv_list(os.getenv("MCP_PROTECTED_NAMESPACES")) or ["kube-system", traefik_ns]
        allowed_ns = _parse_csv_list(os.getenv("MCP_ALLOWED_NAMESPACES"))

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "traefik-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", "0.2.1"),
            transport=os.getenv("MCP_TRANSPORT", "stdio").strip().lower(),
            allow_write=allow_write,
            toolsets=toolsets,
            debug=_parse_bool_env(os.getenv("MCP_DEBUG"), default=False),
            namespace=os.getenv("K8S_NAMESPACE") or os.getenv("MCP_NAMESPACE") or None,
            traefik_namespace=traefik_ns,
            traefik_api_url=os.getenv("TRAEFIK_API_URL") or None,
            traefik_http_url=os.getenv("TRAEFIK_HTTP_URL") or None,
            traefik_https_url=os.getenv("TRAEFIK_HTTPS_URL") or None,
            allowed_namespaces=allowed_ns,
            protected_namespaces=protected_ns,
            field_manager=os.getenv("MCP_FIELD_MANAGER", "talkops-traefik-mcp"),
            cert_expiry_warning_days=int(os.getenv("TRAEFIK_CERT_EXPIRY_WARNING_DAYS", "21")),
            probe_allow_any_host=_parse_bool_env(os.getenv("TRAEFIK_PROBE_ALLOW_ANY_HOST"), default=False),
            log_max_lines=int(os.getenv("TRAEFIK_LOG_MAX_LINES", "5000")),
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
            prog="traefik-mcp-server",
            description="Traefik v3 Traffic Management & Diagnostics MCP Server",
        )
        parser.add_argument(
            "--transport",
            choices=["stdio"],
            default=None,
            help="MCP transport mode (stdio only)",
        )
        parser.add_argument(
            "--toolsets",
            default=None,
            help="Comma-separated toolsets to enable: all,readonly,traffic,policies,diagnostics",
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
            "--traefik-namespace",
            default=None,
            help="Namespace where the Traefik controller runs (default: traefik)",
        )
        parser.add_argument(
            "--traefik-api-url",
            default=None,
            help="Optional direct base URL to Traefik runtime API (defaults to K8s pods/proxy)",
        )
        parser.add_argument(
            "--allowed-namespaces",
            default=None,
            help="Comma-separated allowlist of namespaces permitted for writes",
        )
        parser.add_argument(
            "--protected-namespaces",
            default=None,
            help="Comma-separated list of protected namespaces requiring confirmation",
        )
        parser.add_argument(
            "--field-manager",
            default=None,
            help="Kubernetes Server-Side Apply fieldManager name (default: talkops-traefik-mcp)",
        )
        parser.add_argument(
            "--cert-expiry-warning-days",
            type=int,
            default=None,
            help="Days before TLS certificate expiry to trigger warnings (default: 21)",
        )
        parser.add_argument(
            "--probe-allow-any-host",
            action="store_true",
            default=False,
            help="Allow traefik_trace_request live probes against hosts not present in cluster routes",
        )
        parser.add_argument(
            "--log-max-lines",
            type=int,
            default=None,
            help="Maximum pod log lines fetched during traefik_analyze_logs (default: 5000)",
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
            cfg.transport = args.transport
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
        if args.traefik_namespace is not None:
            cfg.traefik_namespace = args.traefik_namespace
            if cfg.traefik_namespace not in cfg.protected_namespaces:
                cfg.protected_namespaces.append(cfg.traefik_namespace)
        if args.traefik_api_url is not None:
            cfg.traefik_api_url = args.traefik_api_url or None
        if args.allowed_namespaces is not None:
            cfg.allowed_namespaces = _parse_csv_list(args.allowed_namespaces)
        if args.protected_namespaces is not None:
            cfg.protected_namespaces = _parse_csv_list(args.protected_namespaces) or ["kube-system", cfg.traefik_namespace]
        if args.field_manager is not None:
            cfg.field_manager = args.field_manager
        if args.cert_expiry_warning_days is not None:
            cfg.cert_expiry_warning_days = args.cert_expiry_warning_days
        if args.probe_allow_any_host:
            cfg.probe_allow_any_host = True
        if args.log_max_lines is not None:
            cfg.log_max_lines = args.log_max_lines
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
