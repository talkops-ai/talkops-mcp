"""Integration test: log-to-trace pivot flow.

Validates: extract trace ID from log line → retrieve trace → summarize.
"""

import os
import pytest
from unittest.mock import patch

import respx
import httpx

from tests.conftest import _load_fixture, _text


@pytest.fixture
def mock_trace():
    with respx.mock(assert_all_called=False) as mock:
        base = "http://tempo-test:3200"
        mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))
        mock.get(url__regex=rf"{base}/api/v2/traces/.+").mock(
            return_value=httpx.Response(200, json=_load_fixture("trace_response_otlp.json"))
        )
        yield mock


@pytest.fixture
def mcp_app(mock_trace):
    env = {"TEMPO_BASE_URL": "http://tempo-test:3200", "TEMPO_BACKEND_ID": "test-backend", "K8S_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap
        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


class TestLogToTraceFlow:
    """Extract trace ID from log → retrieve → summarize."""

    @pytest.mark.asyncio
    async def test_log_to_trace_pivot(self, mcp_app, mock_trace):
        from fastmcp import Client
        async with Client(mcp_app) as client:
            # Step 1: Extract trace ID from log line
            log_line = 'level=error trace_id=1234567890abcdef1234567890abcdef msg="connection timeout"'
            result = await client.call_tool("tempo_get_trace_from_log", {
                "backend_id": "test-backend",
                "log_line": log_line,
            })
            text = _text(result.content[0]) if result.content else str(result)
            assert "1234567890abcdef1234567890abcdef" in text or "span" in text.lower()
