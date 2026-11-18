"""Layer 2 integration tests for read-only mode tool filtering and dry-run enforcement."""

import json
from typing import Any

import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError


@pytest.mark.asyncio
async def test_readonly_mode_hides_pure_mutation_tools_and_enforces_dry_run(
    mcp_server_readonly: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """In read-only mode, pure mutating tools are unregistered and dry-run tools block dry_run=False."""
    async with Client(mcp_server_readonly) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        # Pure mutation tools must NOT be registered in read-only mode
        for hidden_tool in (
            "create_application",
            "update_application",
            "delete_application",
            "cancel_deployment",
            "onboard_repository",
            "delete_repository",
            "create_project",
            "update_project",
            "delete_project",
        ):
            assert hidden_tool not in tool_names

        # Read-only and dry-run-capable tools remain available (15 tools)
        assert len(tool_names) == 15
        assert "sync_application" in tool_names
        assert "rollback_application" in tool_names

        # dry_run=True succeeds in read-only mode
        sync_preview = await client.call_tool(
            "sync_application",
            {"app_name": "payments-service", "dry_run": True},
        )
        preview_data = (
            sync_preview.data
            if isinstance(getattr(sync_preview, "data", None), dict)
            else json.loads(getattr(sync_preview.content[0], "text", "{}"))
        )
        assert preview_data["mode"] == "dry_run"

        # dry_run=False raises ToolError with MCP_ALLOW_WRITE guidance
        with pytest.raises(ToolError, match="MCP_ALLOW_WRITE=false"):
            await client.call_tool(
                "sync_application",
                {"app_name": "payments-service", "dry_run": False},
            )
