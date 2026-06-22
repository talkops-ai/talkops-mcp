"""E2E workflow test: Sampling Review.

Maps to the otel_sampling_review prompt workflow:
  Inspect sampling → Get collector → Toggle strategy (dry_run)
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_sampling_review_flow(bootstrapped_mcp):
    """End-to-end sampling review workflow."""
    async with Client(bootstrapped_mcp) as client:
        # Step 1 — Get the prompt to understand the workflow
        prompt_result = await client.get_prompt(
            "otel_sampling_review",
            arguments={
                "collector_name": "my-collector",
                "namespace": "observability",
            },
        )
        assert len(prompt_result.messages) > 0
        prompt_text = prompt_result.messages[0].content.text
        assert "otel_inspect_sampling_configuration" in prompt_text

        # Step 2 — Inspect current sampling config
        inspect_result = await client.call_tool(
            "otel_inspect_sampling_configuration",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
            },
        )
        inspect_data = json.loads(inspect_result.content[0].text)
        assert "mode" in inspect_data

        # Step 3 — Get collector to understand pipeline topology
        collector_result = await client.call_tool(
            "otel_get_collector",
            {"namespace": "observability", "name": "my-collector"},
        )
        collector_data = json.loads(collector_result.content[0].text)
        assert collector_data["name"] == "my-collector"

        # Step 4 — Generate a config patch (dry_run)
        toggle_result = await client.call_tool(
            "otel_toggle_sampling_strategy",
            {
                "namespace": "observability",
                "collector_name": "my-collector",
                "target_mode": "head",
                "sample_rate": 0.25,
                "dry_run": True,
            },
        )
        toggle_data = json.loads(toggle_result.content[0].text)
        assert toggle_data["target_mode"] == "head"
        assert toggle_data["dry_run"] is True
        assert "config_patch" in toggle_data
