"""Integration tests for discovery tools (v0.2.0).

Tools tested: loki_get_labels, loki_get_label_values, loki_get_series
"""

import json

import pytest

from tests.conftest import get_text


class TestLokiGetLabels:
    """Tests for the loki_get_labels tool."""

    @pytest.mark.asyncio
    async def test_returns_labels(self, mcp_client):
        result = await mcp_client.call_tool("loki_get_labels", {})
        data = json.loads(get_text(result))
        assert "labels" in data
        assert isinstance(data["labels"], list)
        assert len(data["labels"]) > 0
        assert data["count"] == len(data["labels"])

    @pytest.mark.asyncio
    async def test_contains_expected_labels(self, mcp_client):
        result = await mcp_client.call_tool("loki_get_labels", {})
        data = json.loads(get_text(result))
        assert "app" in data["labels"]
        assert "namespace" in data["labels"]

    @pytest.mark.asyncio
    async def test_with_time_range(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_labels",
            {"start": "now-24h", "end": "now"},
        )
        data = json.loads(get_text(result))
        assert isinstance(data["labels"], list)


class TestLokiGetLabelValues:
    """Tests for the loki_get_label_values tool."""

    @pytest.mark.asyncio
    async def test_returns_values(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_label_values", {"label": "app"}
        )
        data = json.loads(get_text(result))
        assert data["label"] == "app"
        assert isinstance(data["values"], list)
        assert len(data["values"]) > 0
        assert data["count"] == len(data["values"])

    @pytest.mark.asyncio
    async def test_contains_checkout(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_label_values", {"label": "app"}
        )
        data = json.loads(get_text(result))
        assert "checkout" in data["values"]

    @pytest.mark.asyncio
    async def test_with_scope_query(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_label_values",
            {"label": "app", "query": '{namespace="production"}'},
        )
        data = json.loads(get_text(result))
        assert data["label"] == "app"
        assert isinstance(data["values"], list)


class TestLokiGetSeries:
    """Tests for the loki_get_series tool."""

    @pytest.mark.asyncio
    async def test_returns_series(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_series",
            {"match": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert data["matcher"] == '{app="checkout"}'
        assert data["total_series"] > 0
        assert isinstance(data["series"], list)

    @pytest.mark.asyncio
    async def test_returns_label_cardinality(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_series",
            {"match": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "label_cardinality" in data
        assert isinstance(data["label_cardinality"], dict)
        for _, count in data["label_cardinality"].items():
            assert isinstance(count, int)
            assert count > 0

    @pytest.mark.asyncio
    async def test_returns_warnings_list(self, mcp_client):
        result = await mcp_client.call_tool(
            "loki_get_series",
            {"match": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
