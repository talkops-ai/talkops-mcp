"""Prometheus onboarding and instrumentation tools.

Provides granular tools for recommending instrumentation strategies,
generating code snippets, and testing metrics endpoints.
"""

from typing import Any, Dict, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from prometheus_mcp_server.exceptions import PrometheusOperationError
from prometheus_mcp_server.tools.base import BaseTool


# Known exporter-based services
_EXPORTER_SERVICES = {
    "postgres", "mysql", "redis", "mongodb", "nginx", "apache",
    "kafka", "elasticsearch", "memcached", "cassandra", "oracle",
    "mssql", "couchdb", "aerospike", "clickhouse", "pgbouncer",
    "node", "windows", "smartctl", "ipmi", "nvidia", "apc_ups",
    "nats", "activemq", "ibm_mq", "php-fpm", "varnish", "squid",
    "jenkins", "jira", "bitbucket", "bamboo", "confluence",
    "aws", "gcp", "azure", "cloudflare", "github", "blackbox",
    "snmp", "jmx", "statsd", "consul", "zookeeper", "bind",
    "unbound", "powerdns", "openvpn"
}

# Third-party services that natively expose Prometheus metrics
_NATIVE_SERVICES = {
    "ansible", "awx", "app_connect_enterprise", "ballerina", "bfe", "caddy",
    "ceph", "cockroachdb", "collectd", "concourse", "crg_roller_derby_scoreboard",
    "diffusion", "docker", "doorman", "dovecot", "envoy", "etcd", "flink",
    "freebsd", "gitlab", "grafana", "influxdb", "javamelody", "kong", "kubernetes",
    "kube-apiserver", "kubelet", "kube-scheduler", "lavinmq", "linkerd", "mgmt", "midonet",
    "minio", "netdata", "openziti", "pomerium", "pretix", "prometheus", "quobyte",
    "rabbitmq", "robustirc", "rtpengine", "scylladb", "skipper", "skydns",
    "telegraf", "traefik", "triton", "vector", "vernemq", "flux", "xandikos", "zipkin",
    "vllm", "haproxy"
}

# Frameworks with built-in /metrics support
_BUILTIN_FRAMEWORKS = {"spring_boot", "quarkus", "helidon", "micronaut", "dropwizard", "dotnet", "nestjs"}


class OnboardingTools(BaseTool):
    """Application onboarding and instrumentation tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Recommend Instrumentation Strategy",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            )
        )
        async def prom_recommend_instrumentation(
            workload_type: str = Field(
                ..., description="Workload type: custom_app, postgres, nginx, mongodb, etc."
            ),
            language: Optional[str] = Field(
                default=None, description="Language: go, java, python, nodejs"
            ),
            framework: Optional[str] = Field(
                default=None, description="Framework hint: spring_boot, django, express, etc."
            ),
            environment: Optional[str] = Field(
                default=None, description="Environment: kubernetes or vm"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Recommend direct instrumentation vs exporter vs builtin_metrics.

            Use this to determine the best monitoring strategy for a workload
            based on its type, language, and framework. Read-only.

            Returns:
            - {\"strategy\": str, \"rationale\": str,
               \"recommended_client_library\"|\"recommended_exporter_type\": str}

            When NOT to use: For deploying exporters, use prom_install_exporter.

            Common errors:
            - Unknown workload_type: Use a known service name or 'custom_app'.
            """
            try:
                wt = workload_type.lower()

                # Exporter-based services
                if wt in _EXPORTER_SERVICES:
                    return {
                        "strategy": "exporter",
                        "rationale": f"{wt} is a third-party service. Use a dedicated Prometheus exporter.",
                        "recommended_exporter_type": f"{wt}_exporter",
                        "next_steps": [
                            f"Use prom_install_exporter with exporter_type='{wt}_exporter'",
                            "Configure scrape target via prom_apply_servicemonitor",
                        ],
                    }

                # Native metrics support (no exporter needed)
                if wt in _NATIVE_SERVICES:
                    return {
                        "strategy": "native_metrics",
                        "rationale": f"{wt} natively exposes Prometheus metrics out-of-the-box. No exporter or custom instrumentation required.",
                        "next_steps": [
                            "Use prom_test_endpoint to verify the native /metrics endpoint is reachable",
                            "Configure scrape target via prom_apply_servicemonitor",
                        ],
                    }

                # Built-in metrics frameworks
                if framework and framework.lower() in _BUILTIN_FRAMEWORKS:
                    return {
                        "strategy": "builtin_metrics",
                        "rationale": f"{framework} has built-in Prometheus metrics support.",
                        "framework": framework,
                        "next_steps": [
                            f"Enable /metrics endpoint in {framework} config",
                            "Use prom_test_endpoint to verify metrics are exposed",
                            "Configure scrape target via prom_apply_servicemonitor",
                        ],
                    }

                # Custom application → direct instrumentation
                client_libs = {
                    "python": "prometheus_client",
                    "go": "github.com/prometheus/client_golang",
                    "java": "io.micrometer:micrometer-registry-prometheus",
                    "nodejs": "prom-client",
                }
                recommended_lib = client_libs.get(language or "", "prometheus_client")

                return {
                    "strategy": "direct_instrumentation",
                    "rationale": "Custom application — add Prometheus client library directly.",
                    "recommended_client_library": recommended_lib,
                    "next_steps": [
                        "Use prom_test_endpoint to verify metrics endpoint",
                        "Configure scrape target via prom_apply_servicemonitor",
                    ],
                }
            except Exception as e:
                raise PrometheusOperationError(f"Recommendation failed: {e}")


        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Test Metrics Endpoint",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def prom_test_endpoint(
            endpoint_url: str = Field(
                ..., description="URL to test (e.g. 'http://app:8080/metrics')"
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Validate that an endpoint exposes valid Prometheus/OpenMetrics metrics.

            Use this to verify that a metrics endpoint is correctly configured
            and serving valid Prometheus metrics. Makes an outbound HTTP request.

            Returns:
            - {\"ok\": bool, \"metrics_count\": int, \"format\": str, \"errors\": [str]}

            When NOT to use: For verifying exporter health with Prometheus
            up{} series, use prom_verify_exporter instead.

            Common errors:
            - Connection refused: Ensure the endpoint is reachable from the MCP server.
            - Invalid format: Endpoint must serve text/plain with Prometheus metrics.
            """
            try:
                from prometheus_mcp_server.utils.endpoint_tester import test_metrics_endpoint
                result = await test_metrics_endpoint(endpoint_url)
                return result
            except Exception as e:
                raise PrometheusOperationError(f"Endpoint test failed: {e}")
