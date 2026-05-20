"""Application configuration management."""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from prometheus_mcp_server.models.exporter import (
    ExporterConfigField,
    ExporterConfigModel,
    ExporterInfo,
    K8sNuances,
)

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
    verify_ssl: bool = True
    timeout: int = 30


@dataclass
class KubernetesConfig:
    """Kubernetes cluster configuration."""
    context_name: Optional[str] = None
    in_cluster: bool = False
    enabled: bool = True


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
    version: str = '0.1.0'
    transport: str = 'stdio'
    host: str = '0.0.0.0'
    port: int = 8767
    path: str = '/mcp'
    # HTTP server timeout settings (in seconds)
    http_timeout: int = 300
    http_keepalive_timeout: int = 5
    http_connect_timeout: int = 60

    backends: List[BackendConfig] = field(default_factory=lambda: [BackendConfig()])
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


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
        backends_json = os.getenv('PROMETHEUS_BACKENDS')
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
                        verify_ssl=b.get('verify_ssl', True),
                        timeout=b.get('timeout', 30),
                    )
                    for i, b in enumerate(raw_backends)
                ]
            except (json.JSONDecodeError, TypeError):
                backends = [BackendConfig()]
        else:
            # Single backend mode
            backends = [
                BackendConfig(
                    id=os.getenv('PROMETHEUS_BACKEND_ID', 'default'),
                    base_url=os.getenv('PROMETHEUS_BASE_URL', 'http://localhost:9090'),
                    type=os.getenv('PROMETHEUS_TYPE', 'prometheus'),  # type: ignore[arg-type]
                    display_name=os.getenv('PROMETHEUS_DISPLAY_NAME'),
                    auth_header=os.getenv('PROMETHEUS_AUTH_HEADER'),
                    verify_ssl=os.getenv('PROMETHEUS_VERIFY_SSL', 'true').lower() == 'true',
                    timeout=int(os.getenv('PROMETHEUS_TIMEOUT', '30')),
                )
            ]

        return ServerConfig(
            name=os.getenv('MCP_SERVER_NAME', 'prometheus-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.1.0'),
            transport=os.getenv('MCP_TRANSPORT', 'stdio'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8767')),
            path=os.getenv('MCP_PATH', '/mcp'),
            http_timeout=int(os.getenv('MCP_HTTP_TIMEOUT', '300')),
            http_keepalive_timeout=int(os.getenv('MCP_HTTP_KEEPALIVE_TIMEOUT', '5')),
            http_connect_timeout=int(os.getenv('MCP_HTTP_CONNECT_TIMEOUT', '60')),
            backends=backends,
            kubernetes=KubernetesConfig(
                context_name=os.getenv('K8S_CONTEXT'),
                in_cluster=os.getenv('K8S_IN_CLUSTER', 'false').lower() == 'true',
                enabled=os.getenv('K8S_ENABLED', 'true').lower() == 'true',
            ),
            logging=LoggingConfig(
                level=os.getenv('MCP_LOG_LEVEL', 'INFO'),
                format=os.getenv('MCP_LOG_FORMAT', 'json'),
            ),
        )
