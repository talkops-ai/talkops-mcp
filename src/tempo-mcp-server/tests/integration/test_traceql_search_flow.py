"""Integration test: TraceQL search flow end-to-end.

Validates: build query → search → validate compact MCP output shape.
"""

import os
import pytest
from unittest.mock import patch

import respx
import httpx

from tests.conftest import _load_fixture, _text


@pytest.fixture
def mock_search():
    with respx.mock(assert_all_called=False) as mock:
        base = "http://tempo-test:3200"
        mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))
        mock.get(f"{base}/api/search").mock(return_value=httpx.Response(200, json=_load_fixture("search_response.json")))
        mock.get(f"{base}/api/v2/search/tags").mock(return_value=httpx.Response(200, json=_load_fixture("tags_response.json")))
        yield mock


@pytest.fixture
def mcp_app(mock_search):
    env = {"TEMPO_BASE_URL": "http://tempo-test:3200", "TEMPO_BACKEND_ID": "test-backend", "K8S_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap
        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


class TestTraceQLSearchFlow:
    """Full search flow: filter → search → validate results."""

    @pytest.mark.asyncio
    async def test_service_error_search(self, mcp_app, mock_search):
        from fastmcp import Client
        async with Client(mcp_app) as client:
            result = await client.call_tool("tempo_traceql_search", {
                "backend_id": "test-backend",
                "service": "api-gateway",
                "status": "error",
                "since": "1h",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "trace" in text.lower()

    @pytest.mark.asyncio
    async def test_search_with_raw_query(self, mcp_app, mock_search):
        from fastmcp import Client
        async with Client(mcp_app) as client:
            result = await client.call_tool("tempo_traceql_search", {
                "backend_id": "test-backend",
                "query": '{ resource.service.name = "checkout" && status = error }',
                "since": "30m",
                "limit": 5,
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "trace" in text.lower()

    @pytest.mark.asyncio
    async def test_search_with_duration_filter(self, mcp_app, mock_search):
        from fastmcp import Client
        async with Client(mcp_app) as client:
            result = await client.call_tool("tempo_traceql_search", {
                "backend_id": "test-backend",
                "min_duration_ms": 500,
                "since": "2h",
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "trace" in text.lower()
