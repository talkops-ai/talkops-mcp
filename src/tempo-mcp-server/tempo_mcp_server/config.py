"""Application configuration management for Tempo MCP Server."""

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence

VALID_TOOLSETS = frozenset({
    "all",
    "readonly",
    "search",
    "metrics",
    "diagnostics",
    "overrides",
    "operator",
})


def _strip_env(value: Optional[str]) -> Optional[str]:
    """Strip inline comments and surrounding whitespace from a .env value."""
    if value is None:
        return None
    cleaned = re.sub(r"\s*#.*$", "", value).strip()
    return cleaned if cleaned else None


def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    cleaned = _strip_env(value)
    if cleaned is None:
        return default
    return cleaned.lower() in ("1", "true", "yes", "on")


def _parse_toolsets(raw: Optional[str]) -> List[str]:
    cleaned = _strip_env(raw)
    if not cleaned:
        return ["all"]
    items = [item.strip().lower() for item in cleaned.split(",") if item.strip()]
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
class BackendConfig:
    """Configuration for a single Tempo backend."""

    id: str = "default"
    base_url: str = "http://localhost:3200"
    type: Literal["tempo", "tempo-gateway", "unknown"] = "tempo"
    display_name: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    auth_header: Optional[str] = None
    verify_ssl: bool = True
    timeout: int = 30

    # Tenant configuration
    multi_tenant: bool = False
    default_tenant: Optional[str] = None
    tenant_header: str = "X-Scope-OrgID"

    # Deployment mode
    deployment_mode: Literal["monolithic", "microservices", "unknown"] = "unknown"

    # LLM format support (Tempo 2.9+)
    llm_format_supported: bool = True

    # Optional Prometheus URL for precomputed service-graph metrics
    prometheus_url: Optional[str] = None


@dataclass
class QueryPolicyConfig:
    """Query guardrails and defaults for safe searches."""

    max_lookback: str = "168h"                # 7 days
    default_search_limit: int = 20
    max_search_limit: int = 100
    default_spss: int = 3                     # spans per span-set
    max_spss: int = 10
    require_time_range: bool = True
    require_filter_or_query: bool = True
    default_metrics_sampling: Optional[str] = None
    max_metrics_duration: str = "3h"


@dataclass
class TempoOperatorConfig:
    """Tempo Operator CRD configuration."""

    crd_group: str = "tempo.grafana.com"
    crd_api_version: str = "v1alpha1"
    tempostack_plural: str = "tempostacks"
    tempomonolithic_plural: str = "tempomonolithics"


@dataclass
class KubernetesConfig:
    """Kubernetes cluster configuration."""

    kubeconfig: Optional[str] = None
    context_name: Optional[str] = None
    in_cluster: bool = False
    enabled: bool = False


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

    name: str = "tempo-mcp-server"
    version: str = "0.2.1"
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8768
    path: str = "/mcp"

    # Security & toolset gates
    allow_write: bool = False
    toolsets: List[str] = field(default_factory=lambda: ["all"])
    field_manager: str = "talkops-tempo-mcp"
    debug: bool = False

    # HTTP server timeout settings (in seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    # Response size limits (bytes)
    response_size_soft_limit: int = 40_000
    response_size_hard_limit: int = 200_000

    backends: List[BackendConfig] = field(default_factory=lambda: [BackendConfig()])
    prometheus_url: Optional[str] = None
    query_policy: QueryPolicyConfig = field(default_factory=QueryPolicyConfig)
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    tempo_operator: TempoOperatorConfig = field(default_factory=TempoOperatorConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def __post_init__(self) -> None:
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

    def should_register(self, toolset: str, is_write: bool = False) -> bool:
        """Check whether a tool in the given toolset should be registered under this config."""
        active = set(self.toolsets or ["all"])
        if "readonly" in active and is_write:
            return False
        if is_write and not self.allow_write:
            return False
        if "all" in active or "readonly" in active:
            return True
        return toolset.lower() in active


class Config:
    """Configuration loader."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables."""
        from dotenv import load_dotenv

        load_dotenv()

        prom_env_url = _strip_env(os.getenv("PROMETHEUS_BASE_URL")) or _strip_env(os.getenv("PROMETHEUS_URL"))
        backends_json = os.getenv("TEMPO_BACKENDS")
        if backends_json:
            try:
                raw_backends = json.loads(backends_json)
                backends = [
                    BackendConfig(
                        id=b.get("id", f"backend-{i}"),
                        base_url=b.get("base_url", "http://localhost:3200"),
                        type=b.get("type", "tempo"),
                        display_name=b.get("display_name"),
                        labels=b.get("labels", {}),
                        auth_header=b.get("auth_header"),
                        verify_ssl=b.get("verify_ssl", True),
                        timeout=b.get("timeout", 30),
                        multi_tenant=b.get("multi_tenant", False),
                        default_tenant=b.get("default_tenant"),
                        tenant_header=b.get("tenant_header", "X-Scope-OrgID"),
                        deployment_mode=b.get("deployment_mode", "unknown"),
                        llm_format_supported=b.get("llm_format_supported", True),
                        prometheus_url=b.get("prometheus_url"),
                    )
                    for i, b in enumerate(raw_backends)
                ]
            except (json.JSONDecodeError, TypeError):
                backends = [BackendConfig()]
        else:
            backends = [
                BackendConfig(
                    id=_strip_env(os.getenv("TEMPO_BACKEND_ID")) or "default",
                    base_url=(
                        _strip_env(os.getenv("TEMPO_BASE_URL"))
                        or _strip_env(os.getenv("TEMPO_URL"))
                        or "http://localhost:3200"
                    ),
                    type=_strip_env(os.getenv("TEMPO_TYPE")) or "tempo",  # type: ignore[arg-type]
                    display_name=_strip_env(os.getenv("TEMPO_DISPLAY_NAME")),
                    auth_header=_strip_env(os.getenv("TEMPO_AUTH_HEADER")),
                    verify_ssl=(_strip_env(os.getenv("TEMPO_VERIFY_SSL")) or "true").lower() == "true",
                    timeout=int(_strip_env(os.getenv("TEMPO_TIMEOUT")) or "30"),
                    multi_tenant=(_strip_env(os.getenv("TEMPO_MULTI_TENANT")) or "false").lower() == "true",
                    default_tenant=_strip_env(os.getenv("TEMPO_DEFAULT_TENANT")),
                    tenant_header=_strip_env(os.getenv("TEMPO_TENANT_HEADER")) or "X-Scope-OrgID",
                    deployment_mode=_strip_env(os.getenv("TEMPO_DEPLOYMENT_MODE")) or "unknown",  # type: ignore[arg-type]
                    llm_format_supported=(_strip_env(os.getenv("TEMPO_LLM_FORMAT")) or "true").lower() == "true",
                    prometheus_url=prom_env_url,
                )
            ]

        query_policy = QueryPolicyConfig(
            max_lookback=_strip_env(os.getenv("TEMPO_MAX_LOOKBACK")) or "168h",
            default_search_limit=int(_strip_env(os.getenv("TEMPO_DEFAULT_SEARCH_LIMIT")) or "20"),
            max_search_limit=int(_strip_env(os.getenv("TEMPO_MAX_SEARCH_LIMIT")) or "100"),
            default_spss=int(_strip_env(os.getenv("TEMPO_DEFAULT_SPSS")) or "3"),
            max_spss=int(_strip_env(os.getenv("TEMPO_MAX_SPSS")) or "10"),
            require_time_range=(_strip_env(os.getenv("TEMPO_REQUIRE_TIME_RANGE")) or "true").lower() == "true",
            require_filter_or_query=(_strip_env(os.getenv("TEMPO_REQUIRE_FILTER_OR_QUERY")) or "true").lower() == "true",
            default_metrics_sampling=_strip_env(os.getenv("TEMPO_DEFAULT_METRICS_SAMPLING")),
            max_metrics_duration=_strip_env(os.getenv("TEMPO_MAX_METRICS_DURATION")) or "3h",
        )

        allow_write = _parse_bool_env(os.getenv("MCP_ALLOW_WRITE"), default=False)
        if _parse_bool_env(os.getenv("MCP_READ_ONLY"), default=False):
            allow_write = False

        toolsets = _parse_toolsets(os.getenv("MCP_TOOLSETS", "all"))
        if "readonly" in toolsets:
            allow_write = False

        return ServerConfig(
            name=_strip_env(os.getenv("MCP_SERVER_NAME")) or "tempo-mcp-server",
            version=_strip_env(os.getenv("MCP_SERVER_VERSION")) or "0.2.1",
            transport=_strip_env(os.getenv("MCP_TRANSPORT")) or "stdio",
            host=_strip_env(os.getenv("MCP_HOST")) or "0.0.0.0",
            port=int(_strip_env(os.getenv("MCP_PORT")) or "8768"),
            path=_strip_env(os.getenv("MCP_PATH")) or "/mcp",
            allow_write=allow_write,
            toolsets=toolsets,
            field_manager=_strip_env(os.getenv("MCP_FIELD_MANAGER")) or "talkops-tempo-mcp",
            debug=_parse_bool_env(os.getenv("MCP_DEBUG"), default=False),
            http_timeout=int(_strip_env(os.getenv("MCP_HTTP_TIMEOUT")) or "300"),
            http_keepalive_timeout=int(_strip_env(os.getenv("MCP_HTTP_KEEPALIVE_TIMEOUT")) or "5"),
            http_connect_timeout=int(_strip_env(os.getenv("MCP_HTTP_CONNECT_TIMEOUT")) or "60"),
            response_size_soft_limit=int(_strip_env(os.getenv("MCP_RESPONSE_SIZE_SOFT_LIMIT")) or "40000"),
            response_size_hard_limit=int(_strip_env(os.getenv("MCP_RESPONSE_SIZE_HARD_LIMIT")) or "200000"),
            backends=backends,
            prometheus_url=prom_env_url,
            query_policy=query_policy,
            kubernetes=KubernetesConfig(
                kubeconfig=_strip_env(os.getenv("K8S_KUBECONFIG")) or _strip_env(os.getenv("KUBECONFIG")),
                context_name=_strip_env(os.getenv("K8S_CONTEXT")),
                in_cluster=_parse_bool_env(os.getenv("K8S_IN_CLUSTER"), default=False),
                enabled=_parse_bool_env(os.getenv("K8S_ENABLED"), default=False),
            ),
            tempo_operator=TempoOperatorConfig(
                crd_group=_strip_env(os.getenv("TEMPO_CRD_GROUP")) or "tempo.grafana.com",
                crd_api_version=_strip_env(os.getenv("TEMPO_CRD_API_VERSION")) or "v1alpha1",
            ),
            logging=LoggingConfig(
                level=_strip_env(os.getenv("MCP_LOG_LEVEL")) or "INFO",
                format=_strip_env(os.getenv("MCP_LOG_FORMAT")) or "json",
            ),
        )

    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        """Create CLI argument parser."""
        parser = argparse.ArgumentParser(
            prog="tempo-mcp-server",
            description="Grafana Tempo Distributed Tracing & Operator MCP Execution Server",
        )
        parser.add_argument(
            "--transport",
            choices=["stdio", "http", "sse", "streamable-http"],
            default=None,
            help="MCP transport mode (default: stdio)",
        )
        parser.add_argument(
            "--toolsets",
            default=None,
            help="Comma-separated toolsets: all,readonly,search,metrics,diagnostics,overrides,operator",
        )
        parser.add_argument(
            "--allow-write",
            action="store_true",
            default=False,
            help="Enable mutating tools (tempo_patch_tenant_overrides, tempo_apply_operator_cr)",
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            default=False,
            help="Force read-only mode (overrides --allow-write and MCP_ALLOW_WRITE)",
        )
        parser.add_argument(
            "--tempo-url",
            default=None,
            help="Primary Tempo backend base URL override",
        )
        parser.add_argument(
            "--tenant",
            default=None,
            help="Default tenant ID (X-Scope-OrgID) for the primary Tempo backend",
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
            help="Enable Kubernetes discovery and Tempo Operator CRD access",
        )
        parser.add_argument(
            "--field-manager",
            default=None,
            help="Kubernetes Server-Side Apply fieldManager name (default: talkops-tempo-mcp)",
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
        if args.tempo_url and cfg.backends:
            cfg.backends[0].base_url = args.tempo_url
        if args.tenant and cfg.backends:
            cfg.backends[0].default_tenant = args.tenant
            cfg.backends[0].multi_tenant = True
        if args.kubeconfig is not None:
            cfg.kubernetes.kubeconfig = args.kubeconfig
        if args.context is not None:
            cfg.kubernetes.context_name = args.context
        if args.k8s_enabled:
            cfg.kubernetes.enabled = True
        if args.field_manager is not None:
            cfg.field_manager = args.field_manager
        if args.debug:
            cfg.debug = True

        return cfg
