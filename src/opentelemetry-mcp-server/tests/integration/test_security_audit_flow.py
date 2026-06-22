"""E2E workflow test: Security Audit.

Maps to the otel_security_audit prompt workflow:
  Analyze eBPF → List instrumented services → List collectors
"""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_security_audit_flow(bootstrapped_mcp):
    """End-to-end security audit workflow."""
    async with Client(bootstrapped_mcp) as client:
        # Step 1 — Get the prompt to understand the workflow
        prompt_result = await client.get_prompt(
            "otel_security_audit",
            arguments={"namespace": "default"},
        )
        assert len(prompt_result.messages) > 0
        prompt_text = prompt_result.messages[0].content.text
        assert "otel_analyze_ebpf_footprint" in prompt_text

        # Step 2 — Audit eBPF agents
        ebpf_result = await client.call_tool(
            "otel_analyze_ebpf_footprint",
            {"namespace": "default"},
        )
        ebpf_data = json.loads(ebpf_result.content[0].text)
        assert "risk_level" in ebpf_data
        assert "total_ebpf_pods" in ebpf_data

        # Step 3 — List instrumented services
        services_result = await client.call_tool(
            "otel_list_instrumented_services",
            {"namespace": "default"},
        )
        services_data = json.loads(services_result.content[0].text)
        assert "items" in services_data
        assert services_data["total_count"] >= 0

        # Step 4 — List all collectors
        collectors_result = await client.call_tool(
            "otel_list_collectors",
            {"namespace": "default"},
        )
        collectors_data = json.loads(collectors_result.content[0].text)
        assert "items" in collectors_data
