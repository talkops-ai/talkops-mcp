"""In-memory MCP integration test verifying zero prompts are registered (T-I6)."""

import pytest
from fastmcp import Client
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_no_mcp_prompts_registered(fake_argo_service, fake_generator_service):
    mcp = make_test_server(
        allow_write=True,
        toolsets=["all"],
        argo_service=fake_argo_service,
        generator_service=fake_generator_service,
    )
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
        assert len(prompts) == 0
