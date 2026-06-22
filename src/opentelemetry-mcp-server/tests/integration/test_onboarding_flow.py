"""End-to-End Workflow Test: User Onboarding Flow."""

import json
import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_onboarding_flow(bootstrapped_mcp):
    """
    Test the typical onboarding workflow:
    1. Read the onboarding prompt.
    2. Lookup instrumentation for library.
    3. List instrumented services to verify.
    """
    async with Client(bootstrapped_mcp) as client:
        # 1. Read onboarding prompt
        prompt = await client.get_prompt(
            "otel_onboard_service",
            arguments={
                "service_name": "my-service",
                "namespace": "default",
                "language": "java"
            }
        )
        assert len(prompt.messages) > 0

        # 2. Lookup instrumentation
        lookup_res = await client.call_tool(
            "otel_lookup_instrumentation", 
            {"language": "java"}
        )
        assert "java" in lookup_res.content[0].text.lower()

        # 3. Verify services
        services_res = await client.call_tool(
            "otel_list_instrumented_services",
            {"namespace": "default"}
        )
        data = json.loads(services_res.content[0].text)
        items = data.get("items", [])
        assert len(items) > 0
