"""Application configuration management."""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional


def _strip_env(value: Optional[str]) -> Optional[str]:
    """Strip inline comments and surrounding whitespace from a .env value.

    H-01: python-dotenv does not strip unquoted inline comments, so a line
    like ``TEMPO_DEFAULT_TENANT=  # e.g. "my-org"`` is parsed as the literal
    string ``  # e.g. "my-org"`` and injected verbatim into HTTP headers.

    This helper removes everything from the first bare ``#`` character
    (preceded by whitespace or at the start of the remaining text) and
    strips any surrounding whitespace.  Quoted values are left intact.
    Returns ``None`` when the result is empty so callers can use ``or``
    defaulting naturally.
    """
    if value is None:
        return None
    # Remove inline comment: whitespace followed by '#' through end of line
    cleaned = re.sub(r"\s*#.*$", "", value).strip()
    return cleaned if cleaned else None


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
    default_metrics_sampling: Optional[str] = None  # e.g. "fixed-span:0.1"
    max_metrics_duration: str = "3h"              # Tempo query_frontend.metrics.max_duration


@dataclass
class TempoOperatorConfig:
    """Tempo Operator CRD configuration.

    Controls which API group/version is used when interacting with
    TempoStack and TempoMonolithic custom resources.
    """

    crd_group: str = "tempo.grafana.com"
    crd_api_version: str = "v1alpha1"
    tempostack_plural: str = "tempostacks"
    tempomonolithic_plural: str = "tempomonolithics"


@dataclass
class KubernetesConfig:
    """Kubernetes cluster configuration."""

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
    version: str = "0.1.0"
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8768
    path: str = "/mcp"

    # HTTP server timeout settings (in seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    # Response size limits (bytes)
    # Soft limit: Primary defense. Tools compact and truncate their own results
    # to fit within this budget. Set conservatively because FastMCP serializes
    # results twice (TextContent + structured_content), roughly doubling the
    # wire payload (~2.2x). With truncation, 40KB of compacted data carries
    # significantly more information than raw verbose JSON.
    response_size_soft_limit: int = 40_000
    # Hard limit: Safety net only. The ResponseLimitingMiddleware uses this
    # as a last resort. Set generously high to avoid triggering on normally
    # truncated results. When the old gap was only 10KB (soft / 100K hard),
    # the hard limit fired routinely, stripping structuredContent and breaking
    # MCP client-side outputSchema validation.
    response_size_hard_limit: int = 200_000

    backends: List[BackendConfig] = field(default_factory=lambda: [BackendConfig()])
    query_policy: QueryPolicyConfig = field(default_factory=QueryPolicyConfig)
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    tempo_operator: TempoOperatorConfig = field(default_factory=TempoOperatorConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class Config:
    """Configuration loader."""

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables.

        Supports two modes:
        - Single backend: TEMPO_BASE_URL sets a single default backend
        - Multi backend: TEMPO_BACKENDS JSON array defines multiple backends
        """
        from dotenv import load_dotenv

        load_dotenv()

        # Parse backends
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
                    )
                    for i, b in enumerate(raw_backends)
                ]
            except (json.JSONDecodeError, TypeError):
                backends = [BackendConfig()]
        else:
            # Single backend mode
            backends = [
                BackendConfig(
                    id=_strip_env(os.getenv("TEMPO_BACKEND_ID")) or "default",
                    base_url=_strip_env(os.getenv("TEMPO_BASE_URL")) or "http://localhost:3200",
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
                )
            ]

        # Parse query policy
        query_policy = QueryPolicyConfig(
            max_lookback=os.getenv("TEMPO_MAX_LOOKBACK", "168h"),
            default_search_limit=int(os.getenv("TEMPO_DEFAULT_SEARCH_LIMIT", "20")),
            max_search_limit=int(os.getenv("TEMPO_MAX_SEARCH_LIMIT", "100")),
            default_spss=int(os.getenv("TEMPO_DEFAULT_SPSS", "3")),
            max_spss=int(os.getenv("TEMPO_MAX_SPSS", "10")),
            require_time_range=os.getenv("TEMPO_REQUIRE_TIME_RANGE", "true").lower() == "true",
            require_filter_or_query=os.getenv("TEMPO_REQUIRE_FILTER_OR_QUERY", "true").lower() == "true",
            default_metrics_sampling=os.getenv("TEMPO_DEFAULT_METRICS_SAMPLING"),
            max_metrics_duration=os.getenv("TEMPO_MAX_METRICS_DURATION", "3h"),
        )

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "tempo-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", "0.1.0"),
            transport=os.getenv("MCP_TRANSPORT", "stdio"),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8768")),
            path=os.getenv("MCP_PATH", "/mcp"),
            http_timeout=int(os.getenv("MCP_HTTP_TIMEOUT", "300")),
            http_keepalive_timeout=int(os.getenv("MCP_HTTP_KEEPALIVE_TIMEOUT", "5")),
            http_connect_timeout=int(os.getenv("MCP_HTTP_CONNECT_TIMEOUT", "60")),
            response_size_soft_limit=int(os.getenv('MCP_RESPONSE_SIZE_SOFT_LIMIT', '40000')),
            response_size_hard_limit=int(os.getenv('MCP_RESPONSE_SIZE_HARD_LIMIT', '200000')),
            backends=backends,
            query_policy=query_policy,
            kubernetes=KubernetesConfig(
                context_name=os.getenv("K8S_CONTEXT"),
                in_cluster=os.getenv("K8S_IN_CLUSTER", "false").lower() == "true",
                enabled=os.getenv("K8S_ENABLED", "false").lower() == "true",
            ),
            tempo_operator=TempoOperatorConfig(
                crd_group=os.getenv("TEMPO_CRD_GROUP", "tempo.grafana.com"),
                crd_api_version=os.getenv("TEMPO_CRD_API_VERSION", "v1alpha1"),
            ),
            logging=LoggingConfig(
                level=os.getenv("MCP_LOG_LEVEL", "INFO"),
                format=os.getenv("MCP_LOG_FORMAT", "json"),
            ),
        )
