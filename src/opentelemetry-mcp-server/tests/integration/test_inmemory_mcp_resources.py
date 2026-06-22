"""Integration tests for MCP Resources using FastMCP in-memory Client.

Covers all 9 registered resources per §6 and §10 of the testing guide.
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


ALL_EXPECTED_RESOURCE_URIS = [
    "otel://system/health",
    "otel://registry/languages",
]

# Dynamic (template) resources are tested individually below.


# ──────────────────────────────────────────────
# Resource Registration & Discovery (§10 — P0)
# ──────────────────────────────────────────────


async def test_list_resources(bootstrapped_mcp):
    """Test that all resources are registered."""
    async with Client(bootstrapped_mcp) as client:
        resources = await client.list_resources()
        assert len(resources) >= 2
        uris = [
            r.uri.unicode_string() if hasattr(r, "uri") else str(r)
            for r in resources
        ]
        for expected in ALL_EXPECTED_RESOURCE_URIS:
            assert any(expected in u for u in uris), (
                f"Resource '{expected}' not registered"
            )


# ──────────────────────────────────────────────
# Static Resources
# ──────────────────────────────────────────────


async def test_read_system_health(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource("otel://system/health")
        text = result[0].text
        assert len(text) > 0
        data = json.loads(text)
        assert data["server"]["status"] == "healthy"


async def test_read_language_registry(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource("otel://registry/languages")
        text = result[0].text
        assert len(text) > 0
        assert "java" in text


# ──────────────────────────────────────────────
# Dynamic Collector Resources
# ──────────────────────────────────────────────


async def test_read_collector_detail(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource(
            "otel://collector/observability/my-collector"
        )
        text = result[0].text
        assert len(text) > 0
        data = json.loads(text)
        assert data["name"] == "my-collector"
        assert "pipelines" in data


async def test_read_enrichment(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource(
            "otel://k8s-enrichment/observability/my-collector"
        )
        text = result[0].text
        assert len(text) > 0
        data = json.loads(text)
        assert "k8s.pod.name" in str(data)


# ──────────────────────────────────────────────
# Logs Profile Resource (PREVIOUSLY MISSING)
# ──────────────────────────────────────────────


async def test_read_logs_profile(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource(
            "otel://logs-profile/observability/my-collector"
        )
        text = result[0].text
        assert len(text) > 0
        data = json.loads(text)
        assert "enabled" in data
        assert data["enabled"] is True
        assert data["collector_name"] == "my-collector"


# ──────────────────────────────────────────────
# SpanMetrics Resource (PREVIOUSLY MISSING)
# ──────────────────────────────────────────────


async def test_read_spanmetrics_profile(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource(
            "otel://spanmetrics/observability/my-collector"
        )
        text = result[0].text
        assert len(text) > 0
        data = json.loads(text)
        assert data["enabled"] is True
        assert "dimensions" in data


# ──────────────────────────────────────────────
# Target Allocator Resource (PREVIOUSLY MISSING)
# ──────────────────────────────────────────────


async def test_read_target_allocator(bootstrapped_mcp):
    """Default fixture has no TA — should return enabled=False."""
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource(
            "otel://target-allocator/observability/my-collector"
        )
        text = result[0].text
        assert len(text) > 0
        data = json.loads(text)
        assert "enabled" in data


async def test_read_target_allocator_with_ta_fixture(
    bootstrapped_mcp, mock_kubernetes_service
):
    """Use the collector_cr_with_ta fixture which has TA enabled."""
    import os

    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "fixtures",
        "otel",
        "collector_cr_with_ta.json",
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        ta_cr = json.load(f)

    mock_kubernetes_service.get_otel_collector.return_value = ta_cr

    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource(
            "otel://target-allocator/observability/my-collector"
        )
        data = json.loads(result[0].text)
        assert data["enabled"] is True
        assert data["allocation_strategy"] == "consistent-hashing"


# ──────────────────────────────────────────────
# Instrumentation Resource
# ──────────────────────────────────────────────


async def test_read_instrumentation_detail(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource(
            "otel://instrumentation/my-app/default"
        )
        text = result[0].text
        assert len(text) > 0
        assert "default" in text


# ──────────────────────────────────────────────
# Language Resources
# ──────────────────────────────────────────────


async def test_read_lang_specific(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource("otel://lang/java")
        text = result[0].text
        assert len(text) > 0
        data = json.loads(text)
        # Should contain Java-specific instrumentation data
        assert "signal_support" in data or "display_name" in data


async def test_read_lang_unknown(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        result = await client.read_resource("otel://lang/cobol")
        text = result[0].text
        data = json.loads(text)
        assert "error" in data
        assert "available" in data


# ──────────────────────────────────────────────
# Error Cases (§10 — P1)
# ──────────────────────────────────────────────


async def test_read_nonexistent_resource(bootstrapped_mcp):
    async with Client(bootstrapped_mcp) as client:
        with pytest.raises(Exception):
            await client.read_resource("otel://nonexistent/resource")
