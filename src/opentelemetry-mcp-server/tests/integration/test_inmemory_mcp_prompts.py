"""Integration tests verifying zero MCP Prompts are registered (Skill/Execution Separation).

All multi-step workflow playbooks live in Agent Skills (`skills/*/SKILL.md`)
rather than server-side `@mcp.prompt()` handlers.
"""

import pytest
from fastmcp import Client

pytestmark = pytest.mark.asyncio


async def test_zero_prompts_registered(bootstrapped_mcp):
    """T-I2: Server must register 0 MCP prompts."""
    async with Client(bootstrapped_mcp) as client:
        prompts = await client.list_prompts()
        assert len(prompts) == 0, (
            f"Expected 0 MCP prompts (playbooks belong in skills/), found: {[p.name for p in prompts]}"
        )
