"""E2E workflow test: Cardinality Audit.

Maps to the otel_cardinality_audit prompt workflow:
  Detect cardinality → Generate transform rules → Inspect spanmetrics
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_cardinality_audit_flow(bootstrapped_mcp):
    """End-to-end cardinality audit workflow."""
    async with Client(bootstrapped_mcp) as client:
        # Step 1 — Get the prompt to understand the workflow
        prompt_result = await client.get_prompt(
            "otel_cardinality_audit",
            arguments={
                "collector_name": "my-collector",
                "namespace": "observability",
            },
        )
        assert len(prompt_result.messages) > 0
        prompt_text = prompt_result.messages[0].content.text
        assert "otel_detect_cardinality" in prompt_text

        # Step 2 — Detect cardinality issues
        detect_result = await client.call_tool(
            "otel_detect_cardinality",
            {"name": "my-collector", "namespace": "observability"},
        )
        detect_data = json.loads(detect_result.content[0].text)
        assert "issues" in detect_data
        assert detect_data["spanmetrics_enabled"] is True

        # Step 3 — Generate transform rules for remediation
        # Use a known high-cardinality attribute
        transform_result = await client.call_tool(
            "otel_gen_drop_attribute_rules",
            {"attributes": ["http.user_agent"]},
        )
        transform_data = json.loads(transform_result.content[0].text)
        assert "yaml_snippet" in transform_data
        assert "http.user_agent" in transform_data["yaml_snippet"]

        # Step 4 — Inspect spanmetrics for cross-reference
        sm_result = await client.call_tool(
            "otel_inspect_spanmetrics_config",
            {"name": "my-collector", "namespace": "observability"},
        )
        sm_data = json.loads(sm_result.content[0].text)
        assert sm_data["profile"]["enabled"] is True
