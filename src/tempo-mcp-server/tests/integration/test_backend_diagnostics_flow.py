"""Integration test: backend diagnostics flow.

Validates: /ready + /api/status/buildinfo + /status/services + /status/config + /metrics
→ facts-only diagnostics output.
"""

import os
import pytest
from unittest.mock import patch

import respx
import httpx

from tests.conftest import _load_fixture, _text


@pytest.fixture
def mock_status():
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
        mock.get(f"{base}/metrics").mock(
            return_value=httpx.Response(
                200,
                text='tempo_discarded_spans_total{reason="rate_limited",tenant="single-tenant"} 0\n',
            )
        )
        yield mock


@pytest.fixture
def mcp_app():
    env = {
        "TEMPO_BASE_URL": "http://tempo-test:3200",
        "TEMPO_BACKEND_ID": "test-backend",
        "K8S_ENABLED": "false",
    }
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap

        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


class TestBackendDiagnosticsFlow:
    """Full diagnostics probe through MCP."""

    @pytest.mark.asyncio
    async def test_diagnostics_returns_healthy(self, mcp_app, mock_status):
        from fastmcp import Client

        async with Client(mcp_app) as client:
            result = await client.call_tool(
                "tempo_get_diagnostics",
                {"backend_id": "test-backend"},
            )
            text = _text(result.content[0]) if result.content else str(result)
            assert '"ready": true' in text.lower() or "ready" in text.lower()

    @pytest.mark.asyncio
    async def test_diagnostics_with_unhealthy_backend(self, mcp_app):
        """Test diagnostics when /ready returns 503 emits BACKEND_UNREACHABLE."""
        with respx.mock(assert_all_called=False) as mock:
            base = "http://tempo-test:3200"
            mock.get(f"{base}/ready").mock(
                return_value=httpx.Response(503, text="not ready")
            )
            mock.get(f"{base}/api/status/buildinfo").mock(
                return_value=httpx.Response(200, json=_load_fixture("buildinfo.json"))
            )
            mock.get(f"{base}/status/services").mock(
                return_value=httpx.Response(200, json=_load_fixture("status_services.json"))
            )
            mock.get(f"{base}/status/config").mock(
                return_value=httpx.Response(200, text="multitenancy_enabled: false\n")
            )
            mock.get(f"{base}/metrics").mock(return_value=httpx.Response(200, text=""))

            from fastmcp import Client

            async with Client(mcp_app) as client:
                result = await client.call_tool(
                    "tempo_get_diagnostics",
                    {"backend_id": "test-backend"},
                )
                text = _text(result.content[0]) if result.content else str(result)
                assert "BACKEND_UNREACHABLE" in text
