"""Integration tests for the Prometheus MCP server.

Tests full bootstrap, tool registration, and end-to-end tool execution
with mocked Prometheus API via respx.
"""

import json
import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
import respx
from httpx import Response

from prometheus_mcp_server.server.bootstrap import ServerBootstrap
from prometheus_mcp_server.tools import initialize_tools
from prometheus_mcp_server.resources import initialize_resources
from prometheus_mcp_server.prompts import initialize_prompts
from prometheus_mcp_server.services.prometheus_service import PrometheusService
from prometheus_mcp_server.services.kubernetes_service import KubernetesService
from prometheus_mcp_server.config import ServerConfig, BackendConfig, KubernetesConfig, LoggingConfig
from tests.conftest import (
    MOCK_INSTANT_RESPONSE,
    MOCK_METADATA_RESPONSE,
    MOCK_TSDB_STATUS_RESPONSE,
)


# ==========================================
# Bootstrap Integration
# ==========================================

class TestBootstrapIntegration:
    """Test that the full server bootstrap wires all components correctly."""

    def test_full_bootstrap(self):
        env = {
            'PROMETHEUS_BASE_URL': 'http://localhost:9090',
            'PROMETHEUS_VERIFY_SSL': 'false',
            'MCP_TRANSPORT': 'stdio',
            'K8S_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            mcp, config = ServerBootstrap.initialize()
            assert mcp is not None
            assert config.name == 'prometheus-mcp-server'

    def test_bootstrap_multi_backend(self):
        backends = [
            {"id": "dev", "base_url": "http://dev:9090", "type": "prometheus"},
            {"id": "prod", "base_url": "http://prod:9090", "type": "thanos"},
        ]
        env = {
            'PROMETHEUS_BACKENDS': json.dumps(backends),
            'MCP_TRANSPORT': 'stdio',
            'K8S_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            mcp, config = ServerBootstrap.initialize()
            assert len(config.backends) == 2


class TestToolRegistryIntegration:
    """Test that all tool groups register correctly."""

    def test_all_tools_registered(self):
        config = ServerConfig(
            backends=[BackendConfig(id="test", base_url="http://localhost:9090")],
            kubernetes=KubernetesConfig(enabled=False),
        )
        prom_svc = PrometheusService(config)
        k8s_svc = KubernetesService(KubernetesConfig(enabled=False))
        service_locator = {
            "prometheus_service": prom_svc,
            "kubernetes_service": k8s_svc,
            "config": config,
        }
        registry = initialize_tools(service_locator)
        # Should have 9 tool groups registered (v4 refactor: discovery & diagnostics moved to resources)
        assert len(registry.tools) == 9

    def test_all_resources_registered(self):
        config = ServerConfig(
            backends=[BackendConfig(id="test", base_url="http://localhost:9090")],
            kubernetes=KubernetesConfig(enabled=False),
        )
        prom_svc = PrometheusService(config)
        k8s_svc = KubernetesService(KubernetesConfig(enabled=False))
        service_locator = {
            "prometheus_service": prom_svc,
            "kubernetes_service": k8s_svc,
            "config": config,
        }
        registry = initialize_resources(service_locator)
        # Should have 9 resource groups registered (v5: added KubernetesResources)
        assert len(registry.resources) == 9

    def test_all_prompts_registered(self):
        config = ServerConfig(
            backends=[BackendConfig(id="test", base_url="http://localhost:9090")],
            kubernetes=KubernetesConfig(enabled=False),
        )
        prom_svc = PrometheusService(config)
        service_locator = {
            "prometheus_service": prom_svc,
            "kubernetes_service": MagicMock(),
            "config": config,
        }
        registry = initialize_prompts(service_locator)
        # Should have 4 prompt groups registered
        assert len(registry.prompts) == 4


# ==========================================
# End-to-End Tool Execution with Mocked API
# ==========================================

class TestEndToEndQueryExecution:
    """Test tool execution end-to-end with mocked Prometheus API."""

    def setup_method(self):
        self.config = ServerConfig(
            backends=[BackendConfig(
                id="test", base_url="http://localhost:9090",
                verify_ssl=False, timeout=10,
            )],
            kubernetes=KubernetesConfig(enabled=False),
        )
        self.prom_svc = PrometheusService(self.config)

    @respx.mock
    @pytest.mark.asyncio
    async def test_instant_query_e2e(self):
        respx.get("http://localhost:9090/api/v1/metadata").mock(
            return_value=Response(200, json=MOCK_METADATA_RESPONSE)
        )
        respx.get("http://localhost:9090/api/v1/query").mock(
            return_value=Response(200, json=MOCK_INSTANT_RESPONSE)
        )

        # Enforce counter rule should pass for gauge metric
        await self.prom_svc.enforce_counter_rule("test", "up", False)

        # Execute instant query
        result = await self.prom_svc.instant_query("test", "up")
        assert result.resultType == "vector"
        assert result.sample_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_counter_rule_blocks_raw_counter_e2e(self):
        respx.get("http://localhost:9090/api/v1/metadata").mock(
            return_value=Response(200, json=MOCK_METADATA_RESPONSE)
        )

        with pytest.raises(ValueError, match="must be wrapped in rate"):
            await self.prom_svc.enforce_counter_rule(
                "test", "http_requests_total", False
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_counter_rule_blocks_sum_of_raw_counter(self):
        """Test that the improved counter rule catches sum(counter) without rate()."""
        respx.get("http://localhost:9090/api/v1/metadata").mock(
            return_value=Response(200, json=MOCK_METADATA_RESPONSE)
        )

        with pytest.raises(ValueError, match="must be wrapped in rate"):
            await self.prom_svc.enforce_counter_rule(
                "test", "sum(http_requests_total)", False
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_counter_rule_allows_rate_wrapped(self):
        """rate(counter[5m]) should be allowed."""
        respx.get("http://localhost:9090/api/v1/metadata").mock(
            return_value=Response(200, json=MOCK_METADATA_RESPONSE)
        )
        # Should not raise
        await self.prom_svc.enforce_counter_rule(
            "test", "rate(http_requests_total[5m])", False
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_counter_rule_allows_sum_rate(self):
        """sum(rate(counter[5m])) should be allowed because rate() wraps the counter."""
        respx.get("http://localhost:9090/api/v1/metadata").mock(
            return_value=Response(200, json=MOCK_METADATA_RESPONSE)
        )
        await self.prom_svc.enforce_counter_rule(
            "test", "sum(rate(http_requests_total[5m]))", False
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_counter_rule_allows_increase(self):
        """increase(counter[1h]) should be allowed."""
        respx.get("http://localhost:9090/api/v1/metadata").mock(
            return_value=Response(200, json=MOCK_METADATA_RESPONSE)
        )
        await self.prom_svc.enforce_counter_rule(
            "test", "increase(http_requests_total[1h])", False
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_cardinality_e2e(self):
        respx.get("http://localhost:9090/api/v1/status/tsdb").mock(
            return_value=Response(200, json=MOCK_TSDB_STATUS_RESPONSE)
        )

        summary = await self.prom_svc.get_cardinality_summary("test")
        assert summary.overview.total_series == 50000
        assert len(summary.top_cardinality_metrics) == 2


class TestEndToEndToolRegistration:
    """Test that tools register and execute on a real FastMCP instance."""

    def test_tools_register_on_fastmcp(self):
        """Verify tools can be registered on an actual FastMCP instance."""
        env = {
            'PROMETHEUS_BASE_URL': 'http://localhost:9090',
            'PROMETHEUS_VERIFY_SSL': 'false',
            'MCP_TRANSPORT': 'stdio',
            'K8S_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            mcp, config = ServerBootstrap.initialize()
            # If we got here without error, all tools/resources/prompts registered
            assert mcp is not None


class TestEndpointTesterIntegration:
    """Test the shared endpoint tester utility."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_valid_metrics_endpoint(self):
        from prometheus_mcp_server.utils.endpoint_tester import test_metrics_endpoint

        metrics_text = """# HELP up Target is up
# TYPE up gauge
up{job="test"} 1
http_requests_total{method="GET"} 42
"""
        respx.get("http://test-app:8080/metrics").mock(
            return_value=Response(200, text=metrics_text, headers={"content-type": "text/plain"})
        )

        result = await test_metrics_endpoint("http://test-app:8080/metrics")
        assert result["ok"] is True
        assert result["format"] == "prometheus"
        assert "up" in result["metrics_found"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_unreachable_endpoint(self):
        from prometheus_mcp_server.utils.endpoint_tester import test_metrics_endpoint

        respx.get("http://unreachable:8080/metrics").mock(side_effect=Exception("Connection refused"))

        result = await test_metrics_endpoint("http://unreachable:8080/metrics")
        assert result["ok"] is False
        assert len(result["errors"]) > 0


