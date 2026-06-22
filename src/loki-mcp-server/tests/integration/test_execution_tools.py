"""Integration tests for execution and safety tools (v4).

Per test guide §6: Full tool lifecycle through FastMCP client.

v4 Tools tested: get_query_stats, execute_logql_instant, execute_logql_query
"""

import json

import pytest

from tests.conftest import get_text


class TestGetQueryStats:
    """Tests for the get_query_stats tool."""

    @pytest.mark.asyncio
    async def test_returns_stats(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_query_stats",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "streams" in data
        assert "chunks" in data
        assert "entries" in data
        assert "bytes" in data
        assert "human_bytes" in data
        assert "exceeds_threshold" in data
        assert isinstance(data["exceeds_threshold"], bool)

    @pytest.mark.asyncio
    async def test_threshold_included(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_query_stats",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "threshold_bytes" in data
        assert data["threshold_bytes"] > 0


class TestExecuteLogqlInstant:
    """Tests for the execute_logql_instant tool."""

    @pytest.mark.asyncio
    async def test_returns_result(self, mcp_client):
        result = await mcp_client.call_tool(
            "execute_logql_instant",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "result_type" in data
        assert "result" in data
        assert "warnings" in data
        assert isinstance(data["warnings"], list)

    @pytest.mark.asyncio
    async def test_with_time_parameter(self, mcp_client):
        result = await mcp_client.call_tool(
            "execute_logql_instant",
            {"query": '{app="checkout"}', "time": "now"},
        )
        data = json.loads(get_text(result))
        assert "result_type" in data


class TestExecuteLogqlQuery:
    """Tests for the execute_logql_query tool."""

    @pytest.mark.asyncio
    async def test_returns_log_streams(self, mcp_client):
        result = await mcp_client.call_tool(
            "execute_logql_query",
            {
                "query": '{app="checkout"}',
                "start": "now-1h",
                "end": "now",
            },
        )
        data = json.loads(get_text(result))
        assert data["result_type"] == "streams"
        assert "streams" in data
        assert isinstance(data["streams"], list)
        assert "total_lines" in data
        assert "truncated" in data
        assert "warnings" in data

    @pytest.mark.asyncio
    async def test_streams_have_labels_and_entries(self, mcp_client):
        result = await mcp_client.call_tool(
            "execute_logql_query",
            {
                "query": '{app="checkout"}',
                "start": "now-1h",
                "end": "now",
            },
        )
        data = json.loads(get_text(result))
        for stream in data["streams"]:
            assert "labels" in stream
            assert "entries" in stream
            assert isinstance(stream["entries"], list)

    @pytest.mark.asyncio
    async def test_entries_have_timestamp_and_line(self, mcp_client):
        result = await mcp_client.call_tool(
            "execute_logql_query",
            {
                "query": '{app="checkout"}',
                "start": "now-1h",
                "end": "now",
            },
        )
        data = json.loads(get_text(result))
        for stream in data["streams"]:
            for entry in stream["entries"]:
                assert "timestamp" in entry
                assert "line" in entry

    @pytest.mark.asyncio
    async def test_high_cardinality_warning(self, mcp_client):
        """Test that high-cardinality labels in selector produce warnings."""
        result = await mcp_client.call_tool(
            "execute_logql_query",
            {
                "query": '{trace_id="abc123"}',
                "start": "now-1h",
                "end": "now",
            },
        )
        data = json.loads(get_text(result))
        assert len(data["warnings"]) > 0
        assert "high-cardinality" in data["warnings"][0].lower() or \
               "High-cardinality" in data["warnings"][0]

    @pytest.mark.asyncio
    async def test_with_limit(self, mcp_client):
        result = await mcp_client.call_tool(
            "execute_logql_query",
            {
                "query": '{app="checkout"}',
                "start": "now-1h",
                "end": "now",
                "max_log_lines": 5,
            },
        )
        data = json.loads(get_text(result))
        assert data["total_lines"] <= 5
