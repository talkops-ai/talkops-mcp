"""Integration test: Kubernetes discovery flow.

Validates: K8s service discovery → backend listing through MCP.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import respx
import httpx

from tests.conftest import _text


class TestKubernetesDiscoveryFlow:
    """K8s discovery produces backends visible through MCP tools."""

    @pytest.mark.asyncio
    async def test_k8s_disabled_returns_static_backends(self):
        """When K8S_ENABLED=false, only static backends are listed."""
        env = {"TEMPO_BASE_URL": "http://tempo-test:3200", "TEMPO_BACKEND_ID": "test-backend", "K8S_ENABLED": "false"}
        with patch.dict(os.environ, env, clear=False), respx.mock(assert_all_called=False) as mock:
            base = "http://tempo-test:3200"
            mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))

            from tempo_mcp_server.server.bootstrap import ServerBootstrap
            from fastmcp import Client

            mcp, config, _ = ServerBootstrap.initialize()

            async with Client(mcp) as client:
                result = await client.call_tool("tempo_list_backends", {})
                text = _text(result.content[0]) if result.content else str(result)
                assert "test-backend" in text
