"""Application configuration management."""

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence

from prometheus_mcp_server.models.exporter import (
    ExporterConfigField,
    ExporterConfigModel,
    ExporterInfo,
    K8sNuances,
)

VALID_TOOLSETS = frozenset(
    {"all", "readonly", "diagnostics", "query", "rules", "scrape", "exporter"}
)


def _parse_bool_env(raw: Optional[str], *, default: bool = False) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _non_empty_env(*names: str, default: Optional[str] = None) -> Optional[str]:
    """Return the first non-empty stripped environment variable among `names`, else `default`."""
    for name in names:
        val = os.getenv(name)
        if val is not None and val.strip():
            return val.strip()
    return default


def _parse_toolsets(raw: Optional[str]) -> List[str]:
    if not raw or not raw.strip():
        return ["all"]
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return items or ["all"]

# Registry of supported exporters with default configurations
SUPPORTED_EXPORTERS: Dict[str, ExporterInfo] = {
    # 1. node_exporter
    "node_exporter": ExporterInfo(
        type="node_exporter",
        description="Hardware and OS metrics for Linux nodes.",
        supported_environments=["kubernetes", "vm"],
        default_scope="daemonset",
        default_ports={"metrics": 9100},
        image="prom/node-exporter:latest",
        k8s_nuances=K8sNuances(
            requires_rbac=False,
            supports_sidecar=False,
            # Ideally needs hostPath mounts for /proc, /sys
        ),
    ),
    # 2. windows_exporter
    "windows_exporter": ExporterInfo(
        type="windows_exporter",
        description="Metrics for Windows servers and services.",
        supported_environments=["vm"],
        default_scope="daemonset",
        default_ports={"metrics": 9182},
        image="prometheuscommunity/windows-exporter:latest",
    ),
    # 3. kube-state-metrics
    "kube-state-metrics": ExporterInfo(
        type="kube-state-metrics",
        description="Translates Kubernetes object state into metrics via K8s API.",
        supported_environments=["kubernetes"],
        default_scope="deployment",
        default_ports={"metrics": 8080},
        image="registry.k8s.io/kube-state-metrics/kube-state-metrics:latest",
        k8s_nuances=K8sNuances(requires_rbac=True),
    ),
    # 4. elasticsearch_exporter
    "elasticsearch_exporter": ExporterInfo(
        type="elasticsearch_exporter",
        description="Elasticsearch cluster and node metrics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9114},
        image="quay.io/prometheuscommunity/elasticsearch-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="ES_URI", type="string", description="Base URI of ES node/cluster", example="http://elasticsearch:9200", maps_to_flag="--es.uri")
            ],
            optional=[
                ExporterConfigField(name="ES_ALL", type="bool", description="Fetch all nodes", example="true", maps_to_flag="--es.all"),
                ExporterConfigField(name="ES_INDICES", type="bool", description="Enable index-level metrics", example="true", maps_to_flag="--es.indices"),
                ExporterConfigField(name="ES_TIMEOUT", type="string", description="HTTP timeout", example="20s", maps_to_flag="--es.timeout")
            ]
        )
    ),
    # 5. kafka_exporter
    "kafka_exporter": ExporterInfo(
        type="kafka_exporter",
        description="Kafka broker & consumer group lag metrics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9308},
        image="danielqsj/kafka-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="KAFKA_BROKERS", type="string", description="Comma-separated brokers", example="kafka-1:9092,kafka-2:9092", maps_to_flag="--kafka.server")
            ],
            optional=[
                ExporterConfigField(name="KAFKA_SASL_ENABLED", type="bool", description="Enables SASL flags", example="true"),
                ExporterConfigField(name="KAFKA_SASL_USER", type="string", description="SASL username", example="monitoring-user"),
                ExporterConfigField(name="KAFKA_SASL_PASSWORD", type="string", description="SASL password", example="secure-pass"),
                ExporterConfigField(name="KAFKA_TLS_ENABLED", type="bool", description="TLS client mode", example="true")
            ]
        )
    ),
    # 6. rabbitmq_exporter
    "rabbitmq_exporter": ExporterInfo(
        type="rabbitmq_exporter",
        description="RabbitMQ queue & node metrics via HTTP API.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9419},
        image="kbudde/rabbitmq-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="RABBIT_URL", type="string", description="Management HTTP endpoint", example="http://rabbitmq:15672"),
                ExporterConfigField(name="RABBIT_USER", type="string", description="Management user", example="exporter"),
                ExporterConfigField(name="RABBIT_PASSWORD", type="string", description="User password", example="s3cr3t")
            ]
        )
    ),
    # 7. redis_exporter
    "redis_exporter": ExporterInfo(
        type="redis_exporter",
        description="Redis instance and cluster metrics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 9121},
        image="oliver006/redis_exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="REDIS_ADDR", type="string", description="Redis connection string", example="redis://redis:6379", maps_to_flag="--redis.addr")
            ],
            optional=[
                ExporterConfigField(name="REDIS_PASSWORD", type="string", description="For AUTH-enabled Redis", example="password", maps_to_flag="--redis.password"),
                ExporterConfigField(name="REDIS_ALIAS", type="string", description="Prefix / label for metrics", example="cart-cache")
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True)
    ),
    # 8. memcached_exporter
    "memcached_exporter": ExporterInfo(
        type="memcached_exporter",
        description="Memcached server statistics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9150},
        image="prom/memcached-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="MEMCACHED_ADDRESS", type="string", description="Memcached address", example="memcached:11211", maps_to_flag="--memcached.address")
            ],
            optional=[
                ExporterConfigField(name="MEMCACHED_TLS_CA", type="string", description="CA for TLS connections", example="/etc/tls/ca.pem")
            ]
        )
    ),
    # 9. apache_exporter
    "apache_exporter": ExporterInfo(
        type="apache_exporter",
        description="Apache HTTPD mod_status metrics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 9117},
        image="quay.io/prometheuscommunity/apache-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="APACHE_SCRAPE_URI", type="string", description="Status endpoint", example="http://localhost/server-status?auto", maps_to_flag="--scrape_uri")
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True)
    ),
    # 10. php_fpm_exporter
    "php_fpm_exporter": ExporterInfo(
        type="php_fpm_exporter",
        description="PHP-FPM pool metrics (processes, queue).",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 9253},
        image="hipages/php-fpm_exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="PHP_FPM_SCRAPE_URI", type="string", description="FastCGI endpoint", example="tcp://127.0.0.1:9000/status")
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True)
    ),
    # 11. statsd_exporter
    "statsd_exporter": ExporterInfo(
        type="statsd_exporter",
        description="StatsD protocol to Prometheus bridge.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9102, "statsd": 9125},
        image="prom/statsd-exporter:latest",
        config_model=ExporterConfigModel(
            optional=[
                ExporterConfigField(name="STATSD_EXPORTER_MAPPING_CONFIG", type="string", description="YAML mapping config", example="/etc/statsd-exporter/mapping.yml")
            ]
        ),
        k8s_nuances=K8sNuances(requires_udp_service=True, requires_configmap=True, configmap_mount_path="/etc/statsd-exporter")
    ),
    # 12. jmx_exporter
    "jmx_exporter": ExporterInfo(
        type="jmx_exporter",
        description="JMX to Prometheus for JVM apps.",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 5556},
        image="solsson/jmx-prometheus-exporter:latest", # common sidecar image
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="JMX_CONFIG_PATH", type="string", description="MBean to metric mapping", example="/etc/jmx/config.yml")
            ]
        ),
        k8s_nuances=K8sNuances(requires_configmap=True, configmap_mount_path="/etc/jmx", supports_sidecar=True)
    ),
    # 13. aws_cloudwatch_exporter (YACE)
    "aws_cloudwatch_exporter": ExporterInfo(
        type="aws_cloudwatch_exporter",
        description="High-performance AWS CloudWatch metrics exporter (YACE).",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 5000},
        image="quay.io/prometheuscommunity/yet-another-cloudwatch-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="CLOUDWATCH_CONFIG_PATH", type="string", description="YACE Config file", example="/tmp/config.yml", maps_to_flag="--config.file"),
                ExporterConfigField(name="AWS_REGION", type="string", description="Default region", example="eu-west-1")
            ],
            optional=[
                ExporterConfigField(name="AWS_ROLE_ARN", type="string", description="IAM role for cross-account access", example="arn:aws:iam::123:role/yace")
            ]
        ),
        k8s_nuances=K8sNuances(requires_configmap=True, configmap_mount_path="/tmp")
    ),
    # 14. postgres_exporter
    "postgres_exporter": ExporterInfo(
        type="postgres_exporter",
        description="PostgreSQL server metrics (connections, locks, replication).",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 9187},
        image="quay.io/prometheuscommunity/postgres-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="DATA_SOURCE_URI", type="string", description="Host, port, database, SSL mode", example="localhost:5432/postgres?sslmode=disable"),
                ExporterConfigField(name="DATA_SOURCE_USER", type="string", description="DB user for monitoring", example="postgres"),
                ExporterConfigField(name="DATA_SOURCE_PASS", type="string", description="DB password", example="password")
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True)
    ),
    # 15. mysqld_exporter
    "mysqld_exporter": ExporterInfo(
        type="mysqld_exporter",
        description="MySQL server metrics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 9104},
        image="prom/mysqld-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="DATA_SOURCE_NAME", type="string", description="Standard DSN", example="user:password@(mysql:3306)/")
            ],
            optional=[
                ExporterConfigField(name="MYSQLD_ADDRESS", type="string", description="MySQL address", example="mysql:3306", maps_to_flag="--mysqld.address"),
                ExporterConfigField(name="MYSQLD_CONFIG_FILE", type="string", description="MySQL client config", example="/config.my-cnf", maps_to_flag="--config.my-cnf")
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True)
    ),
    # 16. mongodb_exporter
    "mongodb_exporter": ExporterInfo(
        type="mongodb_exporter",
        description="MongoDB instance/cluster metrics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9216},
        image="percona/mongodb_exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="MONGODB_URI", type="string", description="MongoDB URI", example="mongodb://user:pass@mongodb:27017/admin", maps_to_flag="--mongodb.uri")
            ],
            optional=[
                ExporterConfigField(name="MONGODB_USER", type="string", description="Optional explicit user", example="monitor"),
                ExporterConfigField(name="MONGODB_PASSWORD", type="string", description="Optional explicit password", example="secret"),
                ExporterConfigField(name="MONGODB_EXPORTER_COLLECT_ALL", type="bool", description="Collect all metrics", example="true", maps_to_flag="--collect-all")
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True)
    ),
    # 17. nginx_exporter
    "nginx_exporter": ExporterInfo(
        type="nginx_exporter",
        description="NGINX / NGINX Plus metrics.",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 9113},
        image="nginx/nginx-prometheus-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="NGINX_SCRAPE_URI", type="string", description="NGINX stub_status URI", example="http://nginx:8080/stub_status", maps_to_flag="-nginx.scrape-uri")
            ],
            optional=[
                ExporterConfigField(name="NGINX_PLUS", type="bool", description="Use NGINX Plus API", example="true", maps_to_flag="-nginx.plus")
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True)
    ),
    # 18. blackbox_exporter
    "blackbox_exporter": ExporterInfo(
        type="blackbox_exporter",
        description="Probes HTTP/TCP/ICMP/DNS endpoints remotely.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9115},
        image="quay.io/prometheus/blackbox-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="BLACKBOX_CONFIG_PATH", type="string", description="Blackbox config file path", example="/config/blackbox.yml", maps_to_flag="--config.file")
            ]
        ),
        k8s_nuances=K8sNuances(requires_configmap=True, configmap_mount_path="/config"),
        default_config_data='''modules:
  http_2xx:
    prober: http
    timeout: 15s
    http:
      valid_http_versions: ["HTTP/1.1", "HTTP/2.0"]
      valid_status_codes: []
      method: GET
      fail_if_ssl: false
      fail_if_not_ssl: false
  http_post_2xx:
    prober: http
    timeout: 15s
    http:
      valid_http_versions: ["HTTP/1.1", "HTTP/2.0"]
      method: POST
  tcp_connect:
    prober: tcp
    timeout: 15s
  icmp:
    prober: icmp
    timeout: 15s
  dns:
    prober: dns
    timeout: 15s
    dns:
      query_name: "kubernetes.default.svc.cluster.local"
      transport_protocol: "udp"
'''
    ),
    # 19. snmp_exporter
    "snmp_exporter": ExporterInfo(
        type="snmp_exporter",
        description="SNMP to Prometheus bridge.",
        supported_environments=["kubernetes", "vm"],
        default_scope="deployment",
        default_ports={"metrics": 9116},
        image="quay.io/prometheus/snmp-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(name="SNMP_CONFIG_PATH", type="string", description="SNMP config file path", example="/etc/prometheus/snmp/snmp.yml", maps_to_flag="--config.file")
            ],
            optional=[
                ExporterConfigField(name="SNMP_WEB_LISTEN_ADDRESS", type="string", description="Web listen address", example="0.0.0.0:9116", maps_to_flag="--web.listen-address")
            ]
        ),
        k8s_nuances=K8sNuances(requires_configmap=True, configmap_mount_path="/etc/prometheus/snmp")
    ),
    # 20. haproxy_exporter
    "haproxy_exporter": ExporterInfo(
        type="haproxy_exporter",
        description="HAProxy load balancer stats and backend/frontend telemetry exporter.",
        supported_environments=["kubernetes", "vm"],
        default_scope="sidecar",
        default_ports={"metrics": 9101},
        image="quay.io/prometheus/haproxy-exporter:latest",
        config_model=ExporterConfigModel(
            required=[
                ExporterConfigField(
                    name="HAPROXY_SCRAPE_URI",
                    type="string",
                    description="HAProxy stats CSV or socket URI",
                    example="http://haproxy:8404/stats;csv",
                    maps_to_flag="--haproxy.scrape-uri",
                )
            ]
        ),
        k8s_nuances=K8sNuances(supports_sidecar=True),
    ),
}


@dataclass
class BackendConfig:
    """Configuration for a single Prometheus-compatible backend."""
    id: str = "default"
    base_url: str = "http://localhost:9090"
    type: Literal["prometheus", "thanos", "mimir", "cortex", "victoriametrics", "other"] = "prometheus"
    display_name: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    auth_header: Optional[str] = None
    tenant_id: Optional[str] = None
    ruler_url: Optional[str] = None
    verify_ssl: bool = True
    timeout: int = 30


@dataclass
class KubernetesConfig:
    """Kubernetes cluster configuration."""
    context_name: Optional[str] = None
    in_cluster: bool = False
    enabled: bool = True
    kubeconfig: Optional[str] = None


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
    name: str = 'prometheus-mcp-server'
    version: str = '0.2.1'
    transport: str = 'stdio'
    host: str = '0.0.0.0'
    port: int = 8767
    path: str = '/mcp'
    # HTTP server timeout settings (in seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    # Security, toolset scoping & audit settings
    allow_write: bool = True
    toolsets: List[str] = field(default_factory=lambda: ["all"])
    audit_log_path: Optional[str] = None

    # Response size limits (bytes)
    response_size_soft_limit: int = 40_000
    response_size_hard_limit: int = 200_000

    backends: List[BackendConfig] = field(default_factory=lambda: [BackendConfig()])
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
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
        """Return True if a tool in `toolset` should be registered under this config."""
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
        """Load configuration from environment variables.

        Supports two modes:
        - Single backend: PROMETHEUS_BASE_URL sets a single default backend
        - Multi backend: PROMETHEUS_BACKENDS JSON array defines multiple backends
        """
        from dotenv import load_dotenv
        load_dotenv()

        # Parse backends
        backends_json = _non_empty_env('PROMETHEUS_BACKENDS')
        if backends_json:
            try:
                raw_backends = json.loads(backends_json)
                backends = [
                    BackendConfig(
                        id=b.get('id', f'backend-{i}'),
                        base_url=b.get('base_url', 'http://localhost:9090'),
                        type=b.get('type', 'prometheus'),
                        display_name=b.get('display_name'),
                        labels=b.get('labels', {}),
                        auth_header=b.get('auth_header'),
                        tenant_id=b.get('tenant_id'),
                        ruler_url=b.get('ruler_url'),
                        verify_ssl=b.get('verify_ssl', True),
                        timeout=b.get('timeout', 30),
                    )
                    for i, b in enumerate(raw_backends)
                ]
            except (json.JSONDecodeError, TypeError):
                backends = [BackendConfig()]
        else:
            # Single backend mode (accepts PROMETHEUS_BASE_URL or PROMETHEUS_URL)
            backends = [
                BackendConfig(
                    id=_non_empty_env('PROMETHEUS_BACKEND_ID', default='default') or 'default',
                    base_url=_non_empty_env('PROMETHEUS_BASE_URL', 'PROMETHEUS_URL', default='http://localhost:9090') or 'http://localhost:9090',
                    type=_non_empty_env('PROMETHEUS_TYPE', default='prometheus'),  # type: ignore[arg-type]
                    display_name=_non_empty_env('PROMETHEUS_DISPLAY_NAME'),
                    auth_header=_non_empty_env('PROMETHEUS_AUTH_HEADER'),
                    tenant_id=_non_empty_env('PROMETHEUS_TENANT_ID'),
                    ruler_url=_non_empty_env('PROMETHEUS_RULER_URL'),
                    verify_ssl=(_non_empty_env('PROMETHEUS_VERIFY_SSL', default='true') or 'true').lower() == 'true',
                    timeout=int(_non_empty_env('PROMETHEUS_TIMEOUT', default='30') or '30'),
                )
            ]

        allow_write = _parse_bool_env(os.getenv('MCP_ALLOW_WRITE'), default=True)
        if _parse_bool_env(os.getenv('PROMETHEUS_READ_ONLY'), default=False) or _parse_bool_env(
            os.getenv('MCP_READ_ONLY'), default=False
        ):
            allow_write = False

        raw_toolsets = _non_empty_env('PROMETHEUS_TOOLSETS', 'MCP_TOOLSETS', default='all') or 'all'
        toolsets = _parse_toolsets(raw_toolsets)
        if 'readonly' in toolsets:
            allow_write = False

        return ServerConfig(
            name=_non_empty_env('MCP_SERVER_NAME', default='prometheus-mcp-server') or 'prometheus-mcp-server',
            version=_non_empty_env('MCP_SERVER_VERSION', default='0.2.1') or '0.2.1',
            transport=_non_empty_env('MCP_TRANSPORT', default='stdio') or 'stdio',
            host=_non_empty_env('MCP_HOST', default='0.0.0.0') or '0.0.0.0',
            port=int(_non_empty_env('MCP_PORT', default='8767') or '8767'),
            path=_non_empty_env('MCP_PATH', default='/mcp') or '/mcp',
            http_timeout=int(_non_empty_env('MCP_HTTP_TIMEOUT', default='300') or '300'),
            http_keepalive_timeout=int(_non_empty_env('MCP_HTTP_KEEPALIVE_TIMEOUT', default='5') or '5'),
            http_connect_timeout=int(_non_empty_env('MCP_HTTP_CONNECT_TIMEOUT', default='60') or '60'),
            allow_write=allow_write,
            toolsets=toolsets,
            audit_log_path=_non_empty_env('PROMETHEUS_AUDIT_LOG_PATH', 'MCP_AUDIT_LOG_PATH'),
            response_size_soft_limit=int(_non_empty_env('MCP_RESPONSE_SIZE_SOFT_LIMIT', default='40000') or '40000'),
            response_size_hard_limit=int(_non_empty_env('MCP_RESPONSE_SIZE_HARD_LIMIT', default='200000') or '200000'),
            backends=backends,
            kubernetes=KubernetesConfig(
                context_name=_non_empty_env('K8S_CONTEXT', 'KUBE_CONTEXT'),
                in_cluster=(_non_empty_env('K8S_IN_CLUSTER', default='false') or 'false').lower() == 'true',
                enabled=(_non_empty_env('K8S_ENABLED', default='true') or 'true').lower() == 'true',
                kubeconfig=_non_empty_env('K8S_KUBECONFIG', 'KUBECONFIG'),
            ),
            logging=LoggingConfig(
                level=_non_empty_env('MCP_LOG_LEVEL', default='INFO') or 'INFO',
                format=_non_empty_env('MCP_LOG_FORMAT', default='json') or 'json',
            ),
        )

    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        """Create CLI argument parser."""
        parser = argparse.ArgumentParser(
            prog="prometheus-mcp-server",
            description="TalkOps Prometheus & TSDB MCP Execution Server",
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
            help="HTTP bind port (default: 8767)",
        )
        parser.add_argument(
            "--toolsets",
            default=None,
            help="Comma-separated toolsets: all,readonly,diagnostics,query,rules,scrape,exporter",
        )
        parser.add_argument(
            "--allow-write",
            action="store_true",
            default=False,
            help="Enable state-mutating tools (rule upserts, scrape CRDs, exporter installs)",
        )
        parser.add_argument(
            "--read-only",
            action="store_true",
            default=False,
            help="Force read-only mode (disables all mutating/destructive tools)",
        )
        parser.add_argument(
            "--prometheus-url",
            default=None,
            help="Primary Prometheus backend base URL override",
        )
        parser.add_argument(
            "--tenant-id",
            default=None,
            help="Optional X-Scope-OrgID tenant header for Mimir/Cortex/Thanos",
        )
        parser.add_argument(
            "--audit-log-path",
            default=None,
            help="Optional file path for JSONL write audit logging",
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
        if args.host:
            cfg.host = args.host
        if args.port is not None:
            cfg.port = args.port
        if args.toolsets is not None:
            cfg.toolsets = _parse_toolsets(args.toolsets)
        if args.allow_write:
            cfg.allow_write = True
        if args.read_only or "readonly" in cfg.toolsets:
            cfg.allow_write = False
        if args.prometheus_url and cfg.backends:
            cfg.backends[0].base_url = args.prometheus_url
        if args.tenant_id and cfg.backends:
            cfg.backends[0].tenant_id = args.tenant_id
        if args.audit_log_path:
            cfg.audit_log_path = args.audit_log_path

        return cfg
