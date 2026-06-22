"""Integration test: metrics-first triage workflow.

Validates the RED metrics → search → summarize triage pattern.
"""

import os
import pytest
from unittest.mock import patch

import respx
import httpx

from tests.conftest import _load_fixture, _text


@pytest.fixture
def mock_full():
    with respx.mock(assert_all_called=False) as mock:
        base = "http://tempo-test:3200"
        mock.get(f"{base}/ready").mock(return_value=httpx.Response(200, text="ready"))
        mock.get(f"{base}/api/metrics/query_range").mock(return_value=httpx.Response(200, json=_load_fixture("metrics_range_response.json")))
        mock.get(f"{base}/api/search").mock(return_value=httpx.Response(200, json=_load_fixture("search_response.json")))
        mock.get(url__regex=rf"{base}/api/v2/traces/.+").mock(return_value=httpx.Response(200, json=_load_fixture("trace_response_otlp.json")))
        yield mock


@pytest.fixture
def mcp_app(mock_full):
    env = {"TEMPO_BASE_URL": "http://tempo-test:3200", "TEMPO_BACKEND_ID": "test-backend", "K8S_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap
        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


class TestMetricsFirstTriageFlow:
    """RED metrics → search → summarize triage workflow."""

    @pytest.mark.asyncio
    async def test_metrics_to_search_to_summarize(self, mcp_app, mock_full):
        from fastmcp import Client
        async with Client(mcp_app) as client:
            # Step 1: Metrics range query
            metrics = await client.call_tool("tempo_traceql_metrics_range", {
                "backend_id": "test-backend",
                "query": '{ resource.service.name = "api-gateway" && status = error } | rate()',
                "since": "1h",
            })
            metrics_text = _text(metrics.content[0]) if metrics.content else str(metrics)
            assert "result" in metrics_text or "series" in metrics_text

            # Step 2: Search for error traces
            search = await client.call_tool("tempo_traceql_search", {
                "backend_id": "test-backend",
                "service": "api-gateway",
                "status": "error",
                "since": "1h",
            })
            search_text = _text(search.content[0]) if search.content else str(search)
            assert "trace" in search_text.lower()

            # Step 3: Summarize first error trace
            summary = await client.call_tool("tempo_summarize_trace", {
                "backend_id": "test-backend",
                "trace_id": "1234567890abcdef1234567890abcdef",
            })
            summary_text = _text(summary.content[0]) if summary.content else str(summary)
            assert "headline" in summary_text or "errors" in summary_text
