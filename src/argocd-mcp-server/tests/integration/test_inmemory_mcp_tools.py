"""Layer 2 In-Memory FastMCP integration tests for tool discovery, schema limits, annotations, and execution."""

import json
from typing import Any, Dict

import pytest
import respx
from fastmcp import Client

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.server.bootstrap import ServerBootstrap


def _extract_tool_data(result: Any) -> Dict[str, Any]:
    if getattr(result, "data", None) is not None and isinstance(result.data, dict):
        return result.data
    text = result.content[0].text
    return json.loads(text)


EXPECTED_24_TOOLS = {
    # applications (7)
    "list_applications",
    "get_application_details",
    "get_application_resource_tree",
    "create_application",
    "update_application",
    "delete_application",
    "get_application_events",
    # deployments (7)
    "get_application_diff",
    "sync_application",
    "get_sync_status",
    "get_application_logs",
    "rollback_application",
    "refresh_application",
    "cancel_deployment",
    # repositories (5)
    "list_repositories",
    "get_repository",
    "validate_repository_connection",
    "onboard_repository",
    "delete_repository",
    # projects (5)
    "list_projects",
    "get_project",
    "create_project",
    "update_project",
    "delete_project",
}


@pytest.mark.asyncio
async def test_inmemory_tool_catalog_schemas_and_annotations(
    mcp_server_write: Any,
) -> None:
    """Verify exactly 24 tools are registered, each has <= 8 parameters, and zero prompts exist."""
    async with Client(mcp_server_write) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == EXPECTED_24_TOOLS
        assert len(tools) == 24

        for tool in tools:
            props = (tool.inputSchema or {}).get("properties", {})
            assert len(props) <= 8, (
                f"Tool '{tool.name}' has {len(props)} parameters ({list(props.keys())}), exceeding <= 8 limit"
            )
            # Ensure legacy cluster_name is removed from all tools
            assert "cluster_name" not in props, (
                f"Tool '{tool.name}' still exposes legacy 'cluster_name' parameter"
            )
            # Ensure MCP ToolAnnotations are present
            assert tool.annotations is not None, f"Tool '{tool.name}' is missing ToolAnnotations"
            assert tool.annotations.readOnlyHint is not None

        # Verify all 7 legacy prompts have been migrated to Agent Skills
        prompts = await client.list_prompts()
        assert len(prompts) == 0


@pytest.mark.asyncio
async def test_toolset_filtering_via_inmemory_client(
    write_config: ServerConfig,
) -> None:
    """MCP_TOOLSETS=applications,deployments registers only the 14 application & deployment tools."""
    write_config.toolsets = ["applications", "deployments"]
    mcp, _ = ServerBootstrap.initialize(write_config)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert len(tools) == 14
        names = {t.name for t in tools}
        assert "list_applications" in names
        assert "sync_application" in names
        assert "onboard_repository" not in names
        assert "create_project" not in names


@pytest.mark.asyncio
async def test_inmemory_tool_calls_roundtrip(
    mcp_server_write: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """Call representative tools through the full FastMCP JSON-RPC protocol stack."""
    async with Client(mcp_server_write) as client:
        list_res = _extract_tool_data(
            await client.call_tool("list_applications", {"project": "production"})
        )
        assert list_res["total"] == 2

        details_res = _extract_tool_data(
            await client.call_tool(
                "get_application_details",
                {"app_name": "payments-service", "detail_level": "summary"},
            )
        )
        assert details_res["name"] == "payments-service"
        assert details_res["sync_history"][-1]["id"] == 13

        events_res = _extract_tool_data(
            await client.call_tool(
                "get_application_events",
                {"app_name": "payments-service", "warnings_only": True},
            )
        )
        assert events_res["total_events"] == 1
        assert events_res["events"][0]["reason"] == "Unhealthy"

        refresh_res = _extract_tool_data(
            await client.call_tool(
                "refresh_application",
                {"app_name": "payments-service", "mode": "hard"},
            )
        )
        assert refresh_res["refreshed"] is True
        assert refresh_res["mode"] == "hard"
