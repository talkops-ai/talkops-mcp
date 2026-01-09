"""Application configuration management for ArgoFlow MCP Server.

This module provides a comprehensive configuration system for the ArgoFlow MCP server,
including settings for Argo Rollouts, Traefik, Kubernetes, monitoring, and server behavior.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path


@dataclass
class ArgoRolloutsConfig:
    """Argo Rollouts specific configuration.
    
    Configuration for Argo Rollouts operations including timeouts,
    default strategies, and rollout behavior.
    """
    # Operation timeouts (in seconds)
    operation_timeout: int = 300  # 5 minutes
    status_check_interval: int = 5  # 5 seconds
    promotion_timeout: int = 600  # 10 minutes
    
    # Default deployment strategies
    default_strategy: str = 'canary'  # canary, bluegreen, or rolling
    default_replicas: int = 3
    
    # Canary defaults
    default_canary_steps: List[dict] = field(default_factory=lambda: [
        {"setWeight": 10}, {"pause": {"duration": "5m"}},
        {"setWeight": 25}, {"pause": {"duration": "5m"}},
        {"setWeight": 50}, {"pause": {"duration": "5m"}},
        {"setWeight": 75}, {"pause": {"duration": "5m"}},
    ])
    
    # Analysis configuration
    enable_analysis: bool = True
    default_analysis_interval: str = "5m"
    metrics_provider: str = "prometheus"  # prometheus, datadog, newrelic
    
    # Safety settings
    max_concurrent_rollouts: int = 10
    require_manual_promotion: bool = True
    auto_rollback_on_failure: bool = True
    
    # Namespace settings
    watch_namespaces: List[str] = field(default_factory=lambda: ['default'])
    exclude_namespaces: List[str] = field(default_factory=lambda: ['kube-system', 'kube-public'])


@dataclass
class TraefikConfig:
    """Traefik traffic manager configuration.
    
    Configuration for Traefik operations including traffic routing,
    middleware, and circuit breaker settings.
    """
    # Operation settings
    operation_timeout: int = 120  # 2 minutes
    route_sync_interval: int = 10  # 10 seconds
    
    # Traffic management
    default_weight_step: int = 10  # Default weight increment percentage
    max_weight: int = 100
    min_weight: int = 0
    
    # Middleware defaults
    default_rate_limit: int = 100  # requests per second
    default_rate_burst: int = 200
    default_rate_period: str = "1s"
    
    # Circuit breaker defaults
    circuit_breaker_threshold: float = 0.5  # 50% error rate
    circuit_breaker_expression: str = "NetworkErrorRatio() > 0.5"
    
    # Traffic mirroring
    enable_mirroring: bool = True
    default_mirror_percentage: int = 10
    
    # Monitoring
    enable_traffic_metrics: bool = True
    metrics_collection_interval: int = 30  # 30 seconds
    anomaly_detection_threshold: float = 2.0  # Standard deviations
    
    # Safety settings
    max_concurrent_route_updates: int = 5
    validate_before_apply: bool = True


@dataclass
class KubernetesConfig:
    """Kubernetes client configuration.
    
    Configuration for Kubernetes API client including timeouts,
    connection pooling, and authentication.
    """
    # Connection settings
    timeout: int = 30  # API call timeout in seconds
    verify_ssl: bool = True
    connection_pool_size: int = 10
    
    # Kubeconfig settings
    kubeconfig: Optional[str] = None  # Path to kubeconfig, None = auto-detect
    context_name: Optional[str] = None  # Specific context to use
    in_cluster: bool = False  # Force in-cluster config
    
    # API retry settings
    max_retries: int = 3
    retry_backoff: float = 1.0  # Exponential backoff base (seconds)
    
    # Watch settings
    watch_timeout: int = 300  # 5 minutes
    reconnect_on_failure: bool = True
    
    # Resource limits
    max_resources_per_call: int = 100
    
    # Namespace defaults
    default_namespace: str = 'default'
    create_namespace_if_missing: bool = False


@dataclass
class MonitoringConfig:
    """Monitoring and metrics configuration.
    
    Configuration for Prometheus integration, metrics collection,
    and observability features.
    """
    # Prometheus settings
    prometheus_enabled: bool = True
    prometheus_url: str = "http://prometheus:9090"
    prometheus_timeout: int = 30
    
    # Metrics collection
    metrics_enabled: bool = True
    metrics_port: int = 9090
    metrics_path: str = "/metrics"
    
    # Health checks
    health_check_enabled: bool = True
    health_check_port: int = 8080
    health_check_path: str = "/health"
    liveness_check_path: str = "/healthz"
    readiness_check_path: str = "/readyz"
    
    # Logging integration
    log_metrics: bool = True
    metrics_log_interval: int = 60  # Log metrics every 60 seconds
    
    # Cost tracking
    enable_cost_analytics: bool = True
    cost_per_replica_hour: float = 0.05  # USD per replica per hour
    
    # Alerting (webhook endpoints)
    alert_webhooks: List[str] = field(default_factory=list)
    alert_on_rollout_failure: bool = True
    alert_on_traffic_anomaly: bool = True


@dataclass
class LoggingConfig:
    """Logging configuration.
    
    Configuration for application logging including levels,
    formats, and output destinations.
    """
    # Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
    level: str = 'INFO'
    
    # Log format: json, text, structured
    format: str = 'json'
    
    # File logging
    file_enabled: bool = True
    file_path: str = './logs/argoflow_mcp_server.log'
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5
    
    # Console logging
    console_enabled: bool = True
    console_format: str = 'text'  # More readable for console
    
    # Structured logging fields
    include_timestamp: bool = True
    include_caller: bool = True
    include_hostname: bool = True
    
    # Context logging
    log_request_id: bool = True
    log_user_agent: bool = True
    log_client_ip: bool = False  # Privacy consideration
    
    # Performance
    async_logging: bool = True
    buffer_size: int = 1000


@dataclass
class SecurityConfig:
    """Security configuration.
    
    Configuration for authentication, authorization, and security policies.
    """
    # Authentication
    auth_enabled: bool = False
    auth_type: str = 'bearer'  # bearer, basic, oauth2
    api_keys: List[str] = field(default_factory=list)
    
    # Authorization
    rbac_enabled: bool = False
    allowed_namespaces: List[str] = field(default_factory=lambda: ['*'])
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100  # Requests per minute
    rate_limit_burst: int = 200
    
    # CORS
    cors_enabled: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ['*'])
    
    # TLS/SSL
    tls_enabled: bool = False
    tls_cert_file: Optional[str] = None
    tls_key_file: Optional[str] = None


@dataclass
class ServerConfig:
    """Main MCP server configuration.
    
    Root configuration object containing all subsystem configurations
    and server-level settings.
    """
    # Server identity
    name: str = 'argoflow-mcp-server'
    version: str = '0.1.0'
    description: str = 'Argo Rollouts & Traefik Traffic Management MCP Server'
    
    # Transport settings
    transport: str = 'http'  # http (HTTP/SSE) or stdio
    host: str = '0.0.0.0'
    port: int = 8765  # HTTP/SSE server port
    path: str = '/sse'  # SSE endpoint path
    
    # Server behavior
    allow_write: bool = False  # Enable write access for mutating operations
    debug: bool = False
    
    # HTTP server settings
    http_timeout: int = 300  # HTTP request timeout (seconds)
    http_keepalive_timeout: int = 5  # HTTP keepalive timeout (seconds)
    http_connect_timeout: int = 60  # HTTP connection timeout (seconds)
    max_request_size: int = 10485760  # 10MB
    
    # Worker settings
    workers: int = 1  # Number of worker processes
    threads_per_worker: int = 4
    
    # Graceful shutdown
    shutdown_timeout: int = 30  # Seconds to wait for graceful shutdown
    
    # Subsystem configurations
    argo_rollouts: ArgoRolloutsConfig = field(default_factory=ArgoRolloutsConfig)
    traefik: TraefikConfig = field(default_factory=TraefikConfig)
    kubernetes: KubernetesConfig = field(default_factory=KubernetesConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


class Config:
    """Configuration loader with environment variable support.
    
    Loads configuration from environment variables with sensible defaults.
    Supports hierarchical configuration with nested dataclasses.
    """
    
    @staticmethod
    def from_env() -> ServerConfig:
        """Load configuration from environment variables.
        
        Environment variables follow the pattern:
        - Server: MCP_SERVER_NAME, MCP_PORT, etc.
        - Argo: ARGO_DEFAULT_STRATEGY, ARGO_OPERATION_TIMEOUT, etc.
        - Traefik: TRAEFIK_OPERATION_TIMEOUT, TRAEFIK_DEFAULT_WEIGHT_STEP, etc.
        - Kubernetes: K8S_TIMEOUT, K8S_VERIFY_SSL, etc.
        - Monitoring: PROMETHEUS_URL, METRICS_ENABLED, etc.
        - Logging: LOG_LEVEL, LOG_FORMAT, etc.
        - Security: AUTH_ENABLED, RATE_LIMIT_ENABLED, etc.
        
        Returns:
            ServerConfig: Fully configured server configuration
        """
        return ServerConfig(
            # Server settings
            name=os.getenv('MCP_SERVER_NAME', 'argoflow-mcp-server'),
            version=os.getenv('MCP_SERVER_VERSION', '0.1.0'),
            transport=os.getenv('MCP_TRANSPORT', 'http'),
            host=os.getenv('MCP_HOST', '0.0.0.0'),
            port=int(os.getenv('MCP_PORT', '8765')),
            path=os.getenv('MCP_PATH', '/sse'),
            allow_write=os.getenv('MCP_ALLOW_WRITE', 'false').lower() == 'true',
            debug=os.getenv('MCP_DEBUG', 'false').lower() == 'true',
            
            # HTTP settings
            http_timeout=int(os.getenv('MCP_HTTP_TIMEOUT', '300')),
            http_keepalive_timeout=int(os.getenv('MCP_HTTP_KEEPALIVE_TIMEOUT', '5')),
            http_connect_timeout=int(os.getenv('MCP_HTTP_CONNECT_TIMEOUT', '60')),
            max_request_size=int(os.getenv('MCP_MAX_REQUEST_SIZE', '10485760')),
            
            # Worker settings
            workers=int(os.getenv('MCP_WORKERS', '1')),
            threads_per_worker=int(os.getenv('MCP_THREADS_PER_WORKER', '4')),
            shutdown_timeout=int(os.getenv('MCP_SHUTDOWN_TIMEOUT', '30')),
            
            # Argo Rollouts configuration
            argo_rollouts=ArgoRolloutsConfig(
                operation_timeout=int(os.getenv('ARGO_OPERATION_TIMEOUT', '300')),
                status_check_interval=int(os.getenv('ARGO_STATUS_CHECK_INTERVAL', '5')),
                promotion_timeout=int(os.getenv('ARGO_PROMOTION_TIMEOUT', '600')),
                default_strategy=os.getenv('ARGO_DEFAULT_STRATEGY', 'canary'),
                default_replicas=int(os.getenv('ARGO_DEFAULT_REPLICAS', '3')),
                enable_analysis=os.getenv('ARGO_ENABLE_ANALYSIS', 'true').lower() == 'true',
                metrics_provider=os.getenv('ARGO_METRICS_PROVIDER', 'prometheus'),
                require_manual_promotion=os.getenv('ARGO_REQUIRE_MANUAL_PROMOTION', 'true').lower() == 'true',
                auto_rollback_on_failure=os.getenv('ARGO_AUTO_ROLLBACK', 'true').lower() == 'true',
            ),
            
            # Traefik configuration
            traefik=TraefikConfig(
                operation_timeout=int(os.getenv('TRAEFIK_OPERATION_TIMEOUT', '120')),
                route_sync_interval=int(os.getenv('TRAEFIK_ROUTE_SYNC_INTERVAL', '10')),
                default_weight_step=int(os.getenv('TRAEFIK_DEFAULT_WEIGHT_STEP', '10')),
                default_rate_limit=int(os.getenv('TRAEFIK_DEFAULT_RATE_LIMIT', '100')),
                circuit_breaker_threshold=float(os.getenv('TRAEFIK_CIRCUIT_BREAKER_THRESHOLD', '0.5')),
                enable_mirroring=os.getenv('TRAEFIK_ENABLE_MIRRORING', 'true').lower() == 'true',
                enable_traffic_metrics=os.getenv('TRAEFIK_ENABLE_METRICS', 'true').lower() == 'true',
                validate_before_apply=os.getenv('TRAEFIK_VALIDATE_BEFORE_APPLY', 'true').lower() == 'true',
            ),
            
            # Kubernetes configuration
            kubernetes=KubernetesConfig(
                timeout=int(os.getenv('K8S_TIMEOUT', '30')),
                verify_ssl=os.getenv('K8S_VERIFY_SSL', 'true').lower() == 'true',
                connection_pool_size=int(os.getenv('K8S_CONNECTION_POOL_SIZE', '10')),
                kubeconfig=os.getenv('K8S_KUBECONFIG'),
                context_name=os.getenv('K8S_CONTEXT'),
                in_cluster=os.getenv('K8S_IN_CLUSTER', 'false').lower() == 'true',
                max_retries=int(os.getenv('K8S_MAX_RETRIES', '3')),
                default_namespace=os.getenv('K8S_DEFAULT_NAMESPACE', 'default'),
            ),
            
            # Monitoring configuration
            monitoring=MonitoringConfig(
                prometheus_enabled=os.getenv('PROMETHEUS_ENABLED', 'true').lower() == 'true',
                prometheus_url=os.getenv('PROMETHEUS_URL', 'http://prometheus:9090'),
                prometheus_timeout=int(os.getenv('PROMETHEUS_TIMEOUT', '30')),
                metrics_enabled=os.getenv('METRICS_ENABLED', 'true').lower() == 'true',
                metrics_port=int(os.getenv('METRICS_PORT', '9090')),
                health_check_enabled=os.getenv('HEALTH_CHECK_ENABLED', 'true').lower() == 'true',
                health_check_port=int(os.getenv('HEALTH_CHECK_PORT', '8080')),
                enable_cost_analytics=os.getenv('ENABLE_COST_ANALYTICS', 'true').lower() == 'true',
                cost_per_replica_hour=float(os.getenv('COST_PER_REPLICA_HOUR', '0.05')),
            ),
            
            # Logging configuration
            logging=LoggingConfig(
                level=os.getenv('LOG_LEVEL', 'INFO'),
                format=os.getenv('LOG_FORMAT', 'json'),
                file_enabled=os.getenv('LOG_FILE_ENABLED', 'true').lower() == 'true',
                file_path=os.getenv('LOG_FILE_PATH', './logs/argoflow_mcp_server.log'),
                max_bytes=int(os.getenv('LOG_MAX_BYTES', '10485760')),
                console_enabled=os.getenv('LOG_CONSOLE_ENABLED', 'true').lower() == 'true',
            ),
            
            # Security configuration
            security=SecurityConfig(
                auth_enabled=os.getenv('AUTH_ENABLED', 'false').lower() == 'true',
                auth_type=os.getenv('AUTH_TYPE', 'bearer'),
                rbac_enabled=os.getenv('RBAC_ENABLED', 'false').lower() == 'true',
                rate_limit_enabled=os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true',
                rate_limit_requests=int(os.getenv('RATE_LIMIT_REQUESTS', '100')),
                cors_enabled=os.getenv('CORS_ENABLED', 'true').lower() == 'true',
                tls_enabled=os.getenv('TLS_ENABLED', 'false').lower() == 'true',
                tls_cert_file=os.getenv('TLS_CERT_FILE'),
                tls_key_file=os.getenv('TLS_KEY_FILE'),
            ),
        )
    
    @staticmethod
    def from_file(config_file: str) -> ServerConfig:
        """Load configuration from a YAML or JSON file.
        
        Args:
            config_file: Path to configuration file
        
        Returns:
            ServerConfig: Loaded configuration
            
        Note:
            This is a placeholder for future file-based configuration.
            Currently falls back to environment-based configuration.
        """
        # TODO: Implement YAML/JSON config file loading
        # For now, fall back to environment
        return Config.from_env()
    
    @staticmethod
    def get_default() -> ServerConfig:
        """Get default configuration (no environment variables).
        
        Returns:
            ServerConfig: Default configuration
        """
        return ServerConfig()


# Convenience function for loading config
def load_config() -> ServerConfig:
    """Load server configuration from environment.
    
    This is the primary entry point for configuration loading.
    
    Returns:
        ServerConfig: Loaded server configuration
    """
    return Config.from_env()
