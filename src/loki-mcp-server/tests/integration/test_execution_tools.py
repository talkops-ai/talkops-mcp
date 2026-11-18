"""Integration tests for execution and safety tools (v0.2.0).

Tools tested: loki_get_query_stats, loki_query_instant, loki_query_range, loki_query_a2ui
"""

import json

import pytest

from tests.conftest import get_text


class TestLokiGetQueryStats:
    """Tests for the loki_get_query_stats tool."""

    @pytest.mark.asyncio
    async def test_returns_stats(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_query_stats",
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
            "loki_get_query_stats",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "threshold_bytes" in data
        assert data["threshold_bytes"] > 0


class TestLokiQueryInstant:
    """Tests for the loki_query_instant tool."""

    @pytest.mark.asyncio
    async def test_returns_result(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_query_instant",
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
            "loki_query_instant",
            {"query": '{app="checkout"}', "time": "now"},
        )
        data = json.loads(get_text(result))
        assert "result_type" in data


class TestLokiQueryRange:
    """Tests for the loki_query_range tool."""

    @pytest.mark.asyncio
    async def test_returns_log_streams(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_query_range",
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
            "loki_query_range",
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
            "loki_query_range",
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
        result = await mcp_client.call_tool(
            "loki_query_range",
            {
                "query": '{trace_id="abc123"}',
                "start": "now-1h",
                "end": "now",
            },
        )
        data = json.loads(get_text(result))
        assert len(data["warnings"]) > 0
        assert "high-cardinality" in data["warnings"][0].lower()

    @pytest.mark.asyncio
    async def test_with_limit(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_query_range",
            {
                "query": '{app="checkout"}',
                "start": "now-1h",
                "end": "now",
                "max_log_lines": 5,
            },
        )
        data = json.loads(get_text(result))
        assert data["total_lines"] <= 5


class TestLokiQueryA2UI:
    """Tests for the loki_query_a2ui tool."""

    @pytest.mark.asyncio
    async def test_returns_a2ui_log_table_payload(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_query_a2ui",
            {
                "query": '{app="checkout"} |= "error" | json',
                "title": "Checkout Error Logs",
                "start": "now-1h",
                "end": "now",
                "max_log_lines": 10,
            },
        )
        data = json.loads(get_text(result))
        assert data["title"] == "Checkout Error Logs"
        assert "logLines" in data
        assert isinstance(data["logLines"], list)
        if data["logLines"]:
            first = data["logLines"][0]
            assert "timestamp" in first
            assert "severity" in first
            assert "message" in first
