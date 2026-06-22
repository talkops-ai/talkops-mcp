"""End-to-End Workflow Test: Troubleshooting Investigation Flow."""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_investigation_flow(bootstrapped_mcp):
    """
    Test the typical investigation workflow:
    1. Check system health via resource.
    2. Read investigate pipeline prompt.
    3. Get collector config.
    4. Validate k8sattributes order.
    """
    async with Client(bootstrapped_mcp) as client:
        # 1. Check health
        health = await client.read_resource("otel://system/health")
        assert "healthy" in health[0].text

        # 2. Read prompt
        prompt = await client.get_prompt(
            "otel_investigate_pipeline",
            arguments={
                "collector_name": "my-collector",
                "namespace": "observability"
            }
        )
        assert len(prompt.messages) > 0

        # 3. Get collector
        collector_res = await client.call_tool(
            "otel_get_collector",
            {"name": "my-collector", "namespace": "observability"}
        )
        data = json.loads(collector_res.content[0].text)
        assert data["name"] == "my-collector"

        # 4. Validate order
        val_res = await client.call_tool(
            "otel_validate_k8sattributes_order",
            {"name": "my-collector", "namespace": "observability"}
        )
        val_data = json.loads(val_res.content[0].text)
        assert "all_valid" in val_data
