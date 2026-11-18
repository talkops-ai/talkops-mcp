"""Integration tests verifying destructive actions require confirm=True or MCP elicitation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from tests.conftest import make_test_server


def _parse(res) -> dict:
    if hasattr(res, "data") and isinstance(res.data, dict):
        return res.data
    return json.loads(res.content[0].text)


DESTRUCTIVE_CALLS = [
    ("kargo_manage_project", {"action": "delete", "name": "guestbook"}),
    (
        "kargo_delete_resource",
        {"kind": "Stage", "name": "dev", "project": "guestbook"},
    ),
    ("kargo_rollback_stage", {"project": "guestbook", "stage": "dev"}),
    (
        "kargo_approve_freight",
        {"project": "guestbook", "freight_or_alias": "vivid-falcon", "stage": "prod"},
    ),
    (
        "kargo_manage_promotion",
        {"action": "abort", "project": "guestbook", "promotion": "dev.01j9.freight-120"},
    ),
    (
        "kargo_manage_freight",
        {"action": "delete", "project": "guestbook", "freight_or_alias": "vivid-falcon"},
    ),
    (
        "kargo_manage_verification",
        {"action": "abort", "project": "guestbook", "stage": "dev"},
    ),
    (
        "kargo_manage_credentials",
        {"action": "delete", "project": "guestbook", "name": "github-creds"},
    ),
    (
        "kargo_manage_roles",
        {"action": "delete", "project": "guestbook", "role": "dev-promoter"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("tool_name", "base_args"), DESTRUCTIVE_CALLS)
async def test_destructive_tools_cancel_without_confirm_and_succeed_with_confirm(
    tool_name: str,
    base_args: dict,
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        cancelled = _parse(
            await client.call_tool(tool_name, {**base_args, "confirm": False})
        )
        assert cancelled["status"] == "cancelled"

        succeeded = _parse(
            await client.call_tool(tool_name, {**base_args, "confirm": True})
        )
        assert succeeded["status"] == "success"
