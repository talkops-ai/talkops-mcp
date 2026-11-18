"""Integration test verifying zero MCP prompts are registered (skills live in skills/*/SKILL.md)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_zero_mcp_prompts_registered(fake_kargo_service: MagicMock) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
    assert prompts == []
