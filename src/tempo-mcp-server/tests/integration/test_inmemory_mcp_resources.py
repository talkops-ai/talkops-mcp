"""MCP integration tests — all resources via FastMCP in-memory Client.

Validates that every resource URI is readable through the MCP protocol.
"""

import os
import pytest
from unittest.mock import patch

import respx
import httpx

from tests.conftest import _load_fixture, _text


@pytest.fixture
def mock_all_endpoints():
    """Stub all Tempo endpoints for resource reads."""
    with respx.mock(assert_all_called=False) as mock:
        base = "http://tempo-test:3200"
        mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))
        mock.get(f"{base}/api/status/buildinfo").mock(return_value=httpx.Response(200, json=_load_fixture("buildinfo.json")))
        mock.get(f"{base}/status/services").mock(return_value=httpx.Response(200, json=_load_fixture("status_services.json")))
        yield mock


@pytest.fixture
def bootstrapped_mcp(mock_all_endpoints):
    env = {"TEMPO_BASE_URL": "http://tempo-test:3200", "TEMPO_BACKEND_ID": "test-backend", "K8S_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap
        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


class TestStaticResources:
    """Static reference resources readable through MCP."""

    # §11 #10: test_inmemory_resource_read_reference_traceql
    @pytest.mark.asyncio
    async def test_read_traceql_reference(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://reference/traceql")
            text = _text(result[0]) if result else str(result)
            assert "TraceQL" in text or "Selectors" in text

    @pytest.mark.asyncio
    async def test_read_traceql_metrics_reference(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://reference/traceql-metrics")
            text = _text(result[0]) if result else str(result)
            assert "rate()" in text

    @pytest.mark.asyncio
    async def test_read_k8s_attributes_reference(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://reference/k8s-attributes")
            text = _text(result[0]) if result else str(result)
            assert "k8s" in text

    @pytest.mark.asyncio
    async def test_read_query_policies_reference(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://reference/query-policies")
            text = _text(result[0]) if result else str(result)
            assert "limit" in text.lower() or "policy" in text.lower()


class TestRunbookResources:
    """Runbook resources readable through MCP."""

    @pytest.mark.asyncio
    async def test_read_latency_spike_runbook(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://runbooks/latency-spike")
            text = _text(result[0]) if result else str(result)
            assert len(text) > 100

    @pytest.mark.asyncio
    async def test_read_error_burst_runbook(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://runbooks/error-burst")
            text = _text(result[0]) if result else str(result)
            assert len(text) > 100


class TestExamplesResources:
    """Example query resources readable through MCP."""

    @pytest.mark.asyncio
    async def test_read_common_queries(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://examples/common-queries")
            text = _text(result[0]) if result else str(result)
            assert "service.name" in text
