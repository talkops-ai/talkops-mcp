"""Integration tests for structure tools (v4).

Per test guide §6: Full tool lifecycle through FastMCP client.

v4 Tools tested: get_log_patterns, get_detected_fields
"""

import json

import pytest

from tests.conftest import get_text


class TestGetLogPatterns:
    """Tests for the get_log_patterns tool."""

    @pytest.mark.asyncio
    async def test_returns_patterns(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_log_patterns",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "patterns" in data
        assert isinstance(data["patterns"], list)
        assert data["total_patterns"] == len(data["patterns"])

    @pytest.mark.asyncio
    async def test_patterns_have_count(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_log_patterns",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        for pattern in data["patterns"]:
            assert "pattern" in pattern
            assert "total_count" in pattern
            assert isinstance(pattern["total_count"], int)

    @pytest.mark.asyncio
    async def test_patterns_sorted_by_count(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_log_patterns",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        counts = [p["total_count"] for p in data["patterns"]]
        assert counts == sorted(counts, reverse=True)

    @pytest.mark.asyncio
    async def test_suggested_parsers(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_log_patterns",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "suggested_parsers" in data
        assert isinstance(data["suggested_parsers"], list)


class TestGetDetectedFields:
    """Tests for the get_detected_fields tool."""

    @pytest.mark.asyncio
    async def test_returns_fields(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_detected_fields",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        assert "fields" in data
        assert isinstance(data["fields"], list)
        assert data["total_fields"] == len(data["fields"])

    @pytest.mark.asyncio
    async def test_field_structure(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_detected_fields",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        for field in data["fields"]:
            assert "label" in field
            assert "type" in field
            assert "cardinality" in field
            assert "parsers" in field
            assert isinstance(field["parsers"], list)

    @pytest.mark.asyncio
    async def test_field_types_valid(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_detected_fields",
            {"query": '{app="checkout"}'},
        )
        data = json.loads(get_text(result))
        valid_types = {"string", "int", "float", "boolean", "duration", "bytes"}
        for field in data["fields"]:
            assert field["type"] in valid_types

    @pytest.mark.asyncio
    async def test_with_limits(self, mcp_client):
        result = await mcp_client.call_tool(
            "get_detected_fields",
            {
                "query": '{app="checkout"}',
                "line_limit": 50,
                "field_limit": 10,
            },
        )
        data = json.loads(get_text(result))
        assert isinstance(data["fields"], list)
