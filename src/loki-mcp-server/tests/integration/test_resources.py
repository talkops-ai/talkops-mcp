"""Integration tests for dynamic runtime resources (v0.2.0).

Verifies all 9 dynamic loki:// resources and confirms that static
markdown reference resources (loki://reference/*) have been migrated
out of the MCP execution server into Agent Skills.
"""

import json

import pytest

from tests.conftest import get_text


class TestSystemAndConfigResources:
    """Tests for dynamic system, capability, schema, and config resources."""

    @pytest.mark.asyncio
    async def test_capabilities_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://server/capabilities")
        text = get_text(result)
        data = json.loads(text)
        assert data["server"] == "loki-mcp-server"
        assert data["version"] == "0.2.0"
        assert "allow_write" in data
        assert "toolsets" in data
        assert "backend" in data

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


class TestRulesCompactorAndOperatorResources:
    """Tests for dynamic Ruler, Compactor, and Kubernetes Operator resources."""

    @pytest.mark.asyncio
    async def test_rules_groups_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://rules/groups")
        text = get_text(result)
        data = json.loads(text)
        assert "namespaces" in data
        assert "total_groups" in data
        assert "rules" in data

    @pytest.mark.asyncio
    async def test_compactor_delete_requests_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://compactor/delete-requests")
        text = get_text(result)
        data = json.loads(text)
        assert "requests" in data
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_operator_crs_template_resource(self, mcp_client):
        result = await mcp_client.read_resource("loki://operator/crs/logging")
        text = get_text(result)
        data = json.loads(text)
        assert data["namespace"] == "logging"
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_operator_manifest_template_resource(self, mcp_client):
        result = await mcp_client.read_resource(
            "loki://operator/manifests/LokiStack/logging/loki-prod"
        )
        text = get_text(result)
        data = json.loads(text)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_static_reference_resources_removed(self, mcp_client):
        resources = await mcp_client.list_resources()
        uris = {str(r.uri) for r in resources}
        assert "loki://reference/logql" not in uris
        assert "loki://reference/best-practices" not in uris
        assert "loki://reference/query-templates" not in uris
        assert "loki://reference/label-governance" not in uris
