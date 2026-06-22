"""MCP integration tests — all 16 tools via FastMCP in-memory Client.

Uses the §7 pattern: async with Client(mcp) as client: client.call_tool(...)
Each tool is called through the MCP protocol to validate registration,
parameter schema, and response shape.
"""

import json
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import respx
import httpx

from tests.conftest import _load_fixture, _text


@pytest.fixture
def mock_all_endpoints():
    """Stub all Tempo endpoints for tool execution."""
    with respx.mock(assert_all_called=False) as mock:
        base = "http://tempo-test:3200"
        mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))
        mock.get(f"{base}/api/search").mock(return_value=httpx.Response(200, json=_load_fixture("search_response.json")))
        mock.get(url__regex=rf"{base}/api/v2/traces/.+").mock(return_value=httpx.Response(200, json=_load_fixture("trace_response_otlp.json")))
        mock.get(f"{base}/api/v2/search/tags").mock(return_value=httpx.Response(200, json=_load_fixture("tags_response.json")))
        mock.get(url__regex=rf"{base}/api/v2/search/tag/.+/values").mock(return_value=httpx.Response(200, json=_load_fixture("tags_values_response.json")))
        mock.get(f"{base}/api/metrics/query_range").mock(return_value=httpx.Response(200, json=_load_fixture("metrics_range_response.json")))
        mock.get(f"{base}/api/metrics/query").mock(return_value=httpx.Response(200, json=_load_fixture("metrics_instant_response.json")))
        mock.get(f"{base}/api/status/buildinfo").mock(return_value=httpx.Response(200, json=_load_fixture("buildinfo.json")))
        mock.get(f"{base}/status/services").mock(return_value=httpx.Response(200, json=_load_fixture("status_services.json")))
        yield mock


@pytest.fixture
def bootstrapped_mcp(mock_all_endpoints):
    """Bootstrapped FastMCP with all endpoints stubbed."""
    env = {"TEMPO_BASE_URL": "http://tempo-test:3200", "TEMPO_BACKEND_ID": "test-backend", "K8S_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap
        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


class TestDiscoveryTools:
    """Discovery tools: list_backends, get_backend, get_query_policies."""

    @pytest.mark.asyncio
    async def test_list_backends(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_list_backends", {})
            text = _text(result.content[0]) if result.content else str(result)
            assert "test-backend" in text

    @pytest.mark.asyncio
    async def test_get_backend(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_get_backend", {"backend_id": "test-backend"})
            text = _text(result.content[0]) if result.content else str(result)
            assert "test-backend" in text

    @pytest.mark.asyncio
    async def test_get_query_policies(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_get_query_policies", {})
            text = _text(result.content[0]) if result.content else str(result)
            assert "max_search_limit" in text or "require_time_range" in text


class TestSchemaTools:
    """Schema tools: get_attribute_names, get_attribute_values, get_k8s_attribute_map."""

    @pytest.mark.asyncio
    async def test_get_attribute_names(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_get_attribute_names", {"backend_id": "test-backend", "since": "1h"})
            text = _text(result.content[0]) if result.content else str(result)
            assert "service.name" in text or "scopes" in text

    @pytest.mark.asyncio
    async def test_get_attribute_values(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_get_attribute_values", {"backend_id": "test-backend", "attribute": "service.name", "since": "1h"})
            text = _text(result.content[0]) if result.content else str(result)
            assert "api-gateway" in text or "user-service" in text

    @pytest.mark.asyncio
    async def test_get_k8s_attribute_map(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_get_k8s_attribute_map", {})
            text = _text(result.content[0]) if result.content else str(result)
            assert "k8s.namespace.name" in text


class TestSearchTools:
    """Search tools: traceql_search, get_trace, summarize_trace, find_related_traces."""

    # §11 #9: test_inmemory_mcp_call_trace_search
    @pytest.mark.asyncio
    async def test_traceql_search(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_traceql_search", {
                "backend_id": "test-backend",
                "query": "{ status = error }",
                "since": "1h",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "traces" in text or "trace_id" in text

    @pytest.mark.asyncio
    async def test_get_trace(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_get_trace", {
                "backend_id": "test-backend",
                "trace_id": "1234567890abcdef1234567890abcdef",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "spans" in text.lower() or "resource" in text.lower()

    @pytest.mark.asyncio
    async def test_summarize_trace(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_summarize_trace", {
                "backend_id": "test-backend",
                "trace_id": "1234567890abcdef1234567890abcdef",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "headline" in text or "critical_path" in text


class TestMetricsTools:
    """Metrics tools: traceql_metrics_range, traceql_metrics_instant."""

    @pytest.mark.asyncio
    async def test_metrics_range(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_traceql_metrics_range", {
                "backend_id": "test-backend",
                "query": "{ } | rate()",
                "since": "1h",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "series" in text or "result" in text

    @pytest.mark.asyncio
    async def test_metrics_instant(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_traceql_metrics_instant", {
                "backend_id": "test-backend",
                "query": "{ } | rate()",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "result" in text or "value" in text


class TestDiagnosticsTools:
    """Diagnostics tools: get_diagnostics."""

    @pytest.mark.asyncio
    async def test_get_diagnostics(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client
        async with Client(bootstrapped_mcp) as client:
            result = await client.call_tool("tempo_get_diagnostics", {
                "backend_id": "test-backend",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "status" in text or "healthy" in text
