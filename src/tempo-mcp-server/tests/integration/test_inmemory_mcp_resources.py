"""MCP integration tests — all dynamic/live resources via FastMCP in-memory Client.

Validates that every dynamic `tempo://` resource URI is readable through the MCP protocol.
"""

import json
import os
import pytest
from unittest.mock import patch

import respx
import httpx

from tests.conftest import _load_fixture, _text


@pytest.fixture
def mock_all_endpoints():
    """Stub all Tempo endpoints for dynamic resource reads."""
    with respx.mock(assert_all_called=False) as mock:
        base = "http://tempo-test:3200"
        mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))
        mock.get(f"{base}/api/status/buildinfo").mock(
            return_value=httpx.Response(200, json=_load_fixture("buildinfo.json"))
        )
        mock.get(f"{base}/status/services").mock(
            return_value=httpx.Response(200, json=_load_fixture("status_services.json"))
        )
        mock.get(f"{base}/status/config").mock(
            return_value=httpx.Response(
                200,
                text="multitenancy_enabled: false\nmetrics_generator:\n  processors: [service-graphs, span-metrics, local-blocks]\n",
            )
        )
        mock.get(f"{base}/api/v2/search/tags").mock(
            return_value=httpx.Response(200, json=_load_fixture("tags_response.json"))
        )
        mock.get(f"{base}/api/overrides").mock(
            return_value=httpx.Response(
                200,
                json={"max_bytes_per_trace": 5000000},
                headers={"ETag": '"v1"'},
            )
        )
        mock.get(url__regex=rf"{base}/api/v2/traces/.+").mock(
            return_value=httpx.Response(200, json=_load_fixture("trace_response_otlp.json"))
        )
        yield mock


@pytest.fixture
def bootstrapped_mcp(mock_all_endpoints):
    env = {
        "TEMPO_BASE_URL": "http://tempo-test:3200",
        "TEMPO_BACKEND_ID": "test-backend",
        "K8S_ENABLED": "false",
    }
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap

        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


class TestDynamicResources:
    """Dynamic `tempo://` resources readable through MCP."""

    @pytest.mark.asyncio
    async def test_read_server_capabilities(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client

        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://server/capabilities")
            data = json.loads(_text(result[0]))
            assert "allow_write" in data
            assert "toolsets" in data
            assert "query_policy" in data

    @pytest.mark.asyncio
    async def test_read_system_backends(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client

        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://system/backends")
            data = json.loads(_text(result[0]))
            assert isinstance(data, list)
            assert data[0]["id"] == "test-backend"

    @pytest.mark.asyncio
    async def test_read_single_backend(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client

        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://system/backends/test-backend")
            data = json.loads(_text(result[0]))
            assert data["id"] == "test-backend"

    @pytest.mark.asyncio
    async def test_read_deployment_overview(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client

        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://deployment/overview")
            data = json.loads(_text(result[0]))
            assert "backends" in data
            assert "kubernetes_enabled" in data

    @pytest.mark.asyncio
    async def test_read_schema_attributes(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client

        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://schema/test-backend/attributes")
            data = json.loads(_text(result[0]))
            assert "scopes" in data
            assert data["total_attributes"] >= 1

    @pytest.mark.asyncio
    async def test_read_tenant_overrides(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client

        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource("tempo://overrides/test-backend/default")
            data = json.loads(_text(result[0]))
            assert data["etag"] == '"v1"'
            assert data["overrides"]["max_bytes_per_trace"] == 5000000

    @pytest.mark.asyncio
    async def test_read_trace_resource(self, bootstrapped_mcp, mock_all_endpoints):
        from fastmcp import Client

        async with Client(bootstrapped_mcp) as client:
            result = await client.read_resource(
                "tempo://traces/test-backend/1234567890abcdef1234567890abcdef"
            )
            data = json.loads(_text(result[0]))
            assert data["trace_id"] == "1234567890abcdef1234567890abcdef"
            assert "trace" in data
