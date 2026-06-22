"""Integration tests for discovery tools (v4).

Per test guide §6: Full tool lifecycle through FastMCP client,
mocked at the HTTP boundary with respx.

v4 Tools tested: get_cluster_labels, get_label_values, get_active_series
"""

import json

import pytest

from tests.conftest import get_text


class TestGetClusterLabels:
    """Tests for the get_cluster_labels tool."""

    @pytest.mark.asyncio
    async def test_returns_labels(self, mcp_client):
        result = await mcp_client.call_tool("get_cluster_labels", {})
        data = json.loads(get_text(result))
        assert "labels" in data
        assert isinstance(data["labels"], list)
        assert len(data["labels"]) > 0
        assert data["count"] == len(data["labels"])

    @pytest.mark.asyncio
    async def test_contains_expected_labels(self, mcp_client):
        result = await mcp_client.call_tool("get_cluster_labels", {})
        data = json.loads(get_text(result))
        assert "app" in data["labels"]
        assert "namespace" in data["labels"]

    @pytest.mark.asyncio
    async def test_with_time_range(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_cluster_labels",
            {"start": "now-24h", "end": "now"},
        )
        data = json.loads(get_text(result))
        assert isinstance(data["labels"], list)


class TestGetLabelValues:
    """Tests for the get_label_values tool."""

    @pytest.mark.asyncio
    async def test_returns_values(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_label_values", {"label": "app"}
        )
        data = json.loads(get_text(result))
        assert data["label"] == "app"
        assert isinstance(data["values"], list)
        assert len(data["values"]) > 0
        assert data["count"] == len(data["values"])

    @pytest.mark.asyncio
    async def test_contains_checkout(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_label_values", {"label": "app"}
        )
        data = json.loads(get_text(result))
        assert "checkout" in data["values"]

    @pytest.mark.asyncio
    async def test_with_scope_query(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_label_values",
            {"label": "app", "query": '{namespace="production"}'},
        )
        data = json.loads(get_text(result))
        assert data["label"] == "app"
        assert isinstance(data["values"], list)


class TestGetActiveSeries:
    """Tests for the get_active_series tool."""

    @pytest.mark.asyncio
    async def test_returns_series(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_active_series",
            {"match": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert data["matcher"] == '{app="checkout"}'
        assert data["total_series"] > 0
        assert isinstance(data["series"], list)

    @pytest.mark.asyncio
    async def test_returns_label_cardinality(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_active_series",
            {"match": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "label_cardinality" in data
        assert isinstance(data["label_cardinality"], dict)
        # Each value should be an integer count
        for label_name, count in data["label_cardinality"].items():
            assert isinstance(count, int)
            assert count > 0

    @pytest.mark.asyncio
    async def test_returns_warnings_list(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_active_series",
            {"match": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
