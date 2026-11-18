"""Integration tests verifying tool count, <= 8 parameter budgets, ToolAnnotations, and 0->1 secret omission."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from tests.conftest import make_test_server

EXPECTED_ALL_TOOLS = {
    # pipeline (6)
    "kargo_manage_project",
    "kargo_apply_project_config",
    "kargo_apply_warehouse",
    "kargo_apply_stage",
    "kargo_apply_promotion_task",
    "kargo_delete_resource",
    # promotion (7)
    "kargo_query_freight",
    "kargo_refresh",
    "kargo_promote",
    "kargo_rollback_stage",
    "kargo_approve_freight",
    "kargo_manage_promotion",
    "kargo_manage_freight",
    # verification (2)
    "kargo_apply_analysis_template",
    "kargo_manage_verification",
    # credentials (1)
    "kargo_manage_credentials",
    # rbac (1)
    "kargo_manage_roles",
    # diagnostics (3)
    "kargo_trace_freight",
    "kargo_diagnose_stage",
    "kargo_diagnose_warehouse",
}


@pytest.mark.asyncio
async def test_all_20_tools_registered_and_within_8_parameter_budget(
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        tools = await client.list_tools()

    names = {t.name for t in tools}
    assert names == EXPECTED_ALL_TOOLS
    assert len(tools) == 20

    for tool in tools:
        assert tool.description and len(tool.description.strip()) >= 20, (
            f"Tool '{tool.name}' is missing a meaningful description."
        )
        props = (tool.inputSchema or {}).get("properties") or {}
        assert len(props) <= 8, (
            f"Tool '{tool.name}' has {len(props)} parameters ({list(props.keys())}), exceeding <= 8 budget."
        )
        assert tool.annotations is not None, f"Tool '{tool.name}' is missing ToolAnnotations."


@pytest.mark.asyncio
async def test_credentials_tool_omits_raw_secret_parameters(
    fake_kargo_service: MagicMock,
) -> None:
    """Verify 0->1 secret omission: kargo_manage_credentials never accepts raw passwords/tokens/keys."""
    mcp = make_test_server(allow_write=True, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        tools = await client.list_tools()

    cred_tool = next(t for t in tools if t.name == "kargo_manage_credentials")
    schema = cred_tool.inputSchema or {}
    top_props = set((schema.get("properties") or {}).keys())
    defs = schema.get("$defs") or {}
    opt_props = set(((defs.get("CredentialOptions") or {}).get("properties") or {}).keys())
    all_prop_names = {k.lower() for k in (top_props | opt_props)}
    for forbidden in ("password", "token", "ssh_private_key", "sshprivatekey", "raw_token"):
        assert forbidden not in all_prop_names
