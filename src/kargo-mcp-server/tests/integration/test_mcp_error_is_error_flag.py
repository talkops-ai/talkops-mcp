"""Integration tests verifying Kargo API and validation errors surface with isError=True."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from kargo_mcp_server.exceptions import KargoApiError
from tests.conftest import make_test_server


@pytest.mark.asyncio
async def test_api_404_raises_tool_error_with_remediation_guidance(
    fake_kargo_service: MagicMock,
) -> None:
    fake_kargo_service.diagnose_stage = AsyncMock(
        side_effect=KargoApiError(404, "stage 'missing' not found")
    )
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "kargo_diagnose_stage",
                {"project": "guestbook", "stage": "missing"},
            )
    assert "kargo://projects/guestbook/pipeline" in str(exc_info.value)


@pytest.mark.asyncio
async def test_removed_promotion_step_raises_tool_error(
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool(
                "kargo_apply_promotion_task",
                {
                    "project": "guestbook",
                    "name": "bad-task",
                    "steps": [{"uses": "helm-update-image"}],
                    "dry_run": True,
                },
            )
    assert "helm-update-image" in str(exc_info.value)
    assert "yaml-update" in str(exc_info.value)
