"""Application configuration management.

Loads all configuration from environment variables following the 12-Factor
methodology. Uses dataclasses for type-safe, immutable configuration objects.
"""

import os
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass(frozen=True)
class KubernetesConfig:
    """Kubernetes cluster configuration."""

    in_cluster: bool = False
    enabled: bool = True


@dataclass(frozen=True)
class OtelOperatorConfig:
    """OpenTelemetry Operator CRD configuration.

    Controls which API group/version is used when interacting with
    OpenTelemetryCollector and Instrumentation custom resources.

    Note: Collector CRDs and Instrumentation CRDs may use different
    API versions. The OTel Operator promotes these at different rates
    — e.g., Collector reached v1beta1 in Operator v0.86+ while
    Instrumentation remains at v1alpha1.
    """

    crd_group: str = "opentelemetry.io"
    crd_api_version: str = "v1beta1"
    instrumentation_api_version: str = "v1alpha1"
    collector_plural: str = "opentelemetrycollectors"
    instrumentation_plural: str = "instrumentations"


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

    Aggregates all sub-configurations and provides server transport settings.
    """

    name: str = "opentelemetry-mcp-server"
    version: str = "0.1.0"
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8768
    path: str = "/mcp"

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


class Config:
    """Configuration loader.

    Loads all settings from environment variables with sensible defaults.
    Supports dotenv files for local development.
    """

    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables.

        Returns:
            Fully populated ServerConfig instance.
        """
        from dotenv import load_dotenv

        load_dotenv()

        return ServerConfig(
            name=os.getenv("MCP_SERVER_NAME", "opentelemetry-mcp-server"),
            version=os.getenv("MCP_SERVER_VERSION", "0.1.0"),
            transport=os.getenv("MCP_TRANSPORT", "stdio"),
            host=os.getenv("MCP_HOST", "0.0.0.0"),
            port=int(os.getenv("MCP_PORT", "8768")),
            path=os.getenv("MCP_PATH", "/mcp"),
            http_timeout=int(os.getenv("MCP_HTTP_TIMEOUT", "300")),
            http_keepalive_timeout=int(
                os.getenv("MCP_HTTP_KEEPALIVE_TIMEOUT", "5")
            ),
            http_connect_timeout=int(
                os.getenv("MCP_HTTP_CONNECT_TIMEOUT", "60")
            ),
            kubernetes=KubernetesConfig(
                in_cluster=os.getenv("K8S_IN_CLUSTER", "false").lower()
                == "true",
                enabled=os.getenv("K8S_ENABLED", "true").lower() == "true",
            ),
            otel_operator=OtelOperatorConfig(
                crd_group=os.getenv(
                    "OTEL_CRD_GROUP", "opentelemetry.io"
                ),
                crd_api_version=os.getenv(
                    "OTEL_CRD_API_VERSION", "v1beta1"
                ),
                instrumentation_api_version=os.getenv(
                    "OTEL_INSTRUMENTATION_API_VERSION", "v1alpha1"
                ),
                collector_plural=os.getenv(
                    "OTEL_COLLECTOR_PLURAL", "opentelemetrycollectors"
                ),
                instrumentation_plural=os.getenv(
                    "OTEL_INSTRUMENTATION_PLURAL", "instrumentations"
                ),
            ),
            target_allocator=TargetAllocatorConfig(
                service_discovery_enabled=os.getenv(
                    "OTEL_TA_SERVICE_DISCOVERY", "true"
                ).lower()
                == "true",
                default_port=int(
                    os.getenv("OTEL_TA_DEFAULT_PORT", "8080")
                ),
            ),
            prometheus=PrometheusIntegrationConfig(
                base_url=os.getenv("PROMETHEUS_BASE_URL"),
                timeout=int(os.getenv("PROMETHEUS_TIMEOUT", "30")),
                verify_ssl=os.getenv(
                    "PROMETHEUS_VERIFY_SSL", "true"
                ).lower()
                == "true",
            ),
            logging=LoggingConfig(
                level=os.getenv("MCP_LOG_LEVEL", "INFO"),
                format=os.getenv("MCP_LOG_FORMAT", "json"),  # type: ignore[arg-type]
            ),
        )
