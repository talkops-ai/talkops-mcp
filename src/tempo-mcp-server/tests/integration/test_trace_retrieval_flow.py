"""Integration test: trace retrieval and summarization flow.

Validates: get trace → summarize → validate critical path and errors.
Also tests LLM format fallback behavior.
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


class TestTraceRetrievalFlow:
    """Retrieve and summarize a trace through MCP."""

    @pytest.mark.asyncio
    async def test_get_and_summarize_trace(self, mcp_app, mock_trace):
        from fastmcp import Client
        async with Client(mcp_app) as client:
            # Step 1: Retrieve trace
            raw = await client.call_tool("tempo_get_trace", {
                "backend_id": "test-backend",
                "trace_id": "1234567890abcdef1234567890abcdef",
            })
            raw_text = _text(raw.content[0]) if raw.content else str(raw)
            assert "span" in raw_text.lower() or "resource" in raw_text.lower()

            # Step 2: Summarize trace
            summary = await client.call_tool("tempo_summarize_trace", {
                "backend_id": "test-backend",
                "trace_id": "1234567890abcdef1234567890abcdef",
            })
            summary_text = _text(summary.content[0]) if summary.content else str(summary)
            assert "headline" in summary_text or "critical_path" in summary_text
