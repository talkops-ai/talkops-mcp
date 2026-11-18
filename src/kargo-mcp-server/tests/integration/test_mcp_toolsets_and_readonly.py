"""Integration tests verifying read-only mode and --toolsets registration filtering."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from tests.conftest import make_test_server

READ_ONLY_TOOLS = {
    "kargo_query_freight",
    "kargo_trace_freight",
    "kargo_diagnose_stage",
    "kargo_diagnose_warehouse",
}


@pytest.mark.asyncio
async def test_read_only_mode_exposes_only_4_read_tools(
    fake_kargo_service: MagicMock,
) -> None:
    mcp = make_test_server(allow_write=False, kargo_service=fake_kargo_service)
    async with Client(mcp) as client:
        tools = await client.list_tools()

    names = {t.name for t in tools}
    assert names == READ_ONLY_TOOLS


@pytest.mark.asyncio
async def test_toolset_filtering_registers_only_selected_toolsets(
    fake_kargo_service: MagicMock,
) -> None:
    mcp_diag = make_test_server(
        allow_write=True,
        toolsets={"diagnostics"},
        kargo_service=fake_kargo_service,
    )
    async with Client(mcp_diag) as client:
        diag_tools = {t.name for t in await client.list_tools()}
    assert diag_tools == {
        "kargo_trace_freight",
        "kargo_diagnose_stage",
        "kargo_diagnose_warehouse",
    }

    mcp_sec = make_test_server(
        allow_write=True,
        toolsets={"credentials", "rbac"},
        kargo_service=fake_kargo_service,
    )
    async with Client(mcp_sec) as client:
        sec_tools = {t.name for t in await client.list_tools()}
    assert sec_tools == {"kargo_manage_credentials", "kargo_manage_roles"}
