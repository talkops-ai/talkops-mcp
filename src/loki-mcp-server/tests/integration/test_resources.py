"""Integration tests for resources (v4).

Per test guide §6 & §10: Every resource tested through FastMCP client.

v4 Resources tested: 8 resources
"""

import json

import pytest

from tests.conftest import get_text


class TestSystemResources:
    """Tests for system and config resources."""

    @pytest.mark.asyncio
    async def test_health_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://system/health")
        text = get_text(result)
        data = json.loads(text)
        assert "reachable" in data
        assert isinstance(data["reachable"], bool)

    @pytest.mark.asyncio
    async def test_label_schema_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://schema/labels")
        text = get_text(result)
        data = json.loads(text)
        assert "labels" in data
        assert "count" in data
        assert isinstance(data["labels"], list)

    @pytest.mark.asyncio
    async def test_guardrails_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://config/guardrails")
        text = get_text(result)
        data = json.loads(text)
        assert "max_query_bytes" in data
        assert "max_time_window_hours" in data
        assert "max_log_limit" in data
        assert "high_cardinality_threshold" in data

    @pytest.mark.asyncio
    async def test_backends_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://config/backends")
        text = get_text(result)
        data = json.loads(text)
        assert "backend" in data
        backend = data["backend"]
        assert "url" in backend
        assert "timeout_seconds" in backend
        assert "auth_type" in backend


class TestReferenceResources:
    """Tests for reference/documentation resources."""

    @pytest.mark.asyncio
    async def test_logql_reference(self, mcp_client):
        result = await mcp_client.read_resource("loki://reference/logql")
        text = get_text(result)
        assert len(text) > 100
        assert "LogQL" in text or "logql" in text.lower()

    @pytest.mark.asyncio
    async def test_best_practices(self, mcp_client):
        result = await mcp_client.read_resource(
            "loki://reference/best-practices"
        )
        text = get_text(result)
        assert len(text) > 100

    @pytest.mark.asyncio
    async def test_query_templates(self, mcp_client):
        result = await mcp_client.read_resource(
            "loki://reference/query-templates"
        )
        text = get_text(result)
        assert len(text) > 100
        assert "logql" in text.lower() or "query" in text.lower()

    @pytest.mark.asyncio
    async def test_label_governance(self, mcp_client):
        result = await mcp_client.read_resource(
            "loki://reference/label-governance"
        )
        text = get_text(result)
        assert len(text) > 100
        assert "cardinality" in text.lower() or "label" in text.lower()
