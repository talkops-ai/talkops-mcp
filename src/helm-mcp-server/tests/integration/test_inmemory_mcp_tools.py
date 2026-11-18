"""In-memory FastMCP integration tests for all 13 MCP tools, toolset tag filtering, and zero prompts."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from tests.conftest import get_text

EXPECTED_READ_AND_SESSION_TOOLS = {
    "helm_search_charts",
    "helm_list_releases",
    "helm_get_release_status",
    "helm_render_manifests",
    "helm_plan_release",
    "helm_monitor_deployment",
    "kubernetes_check_prerequisites",
    "kubernetes_set_context",
}

EXPECTED_MUTATE_TOOLS = {
    "helm_ensure_repository",
    "helm_install_chart",
    "helm_upgrade_release",
    "helm_rollback_release",
    "helm_uninstall_release",
}

EXPECTED_ALL_TOOLS = EXPECTED_READ_AND_SESSION_TOOLS | EXPECTED_MUTATE_TOOLS

DELETED_LEGACY_TOOLS = {
    "helm_get_chart_info",
    "helm_get_chart_values",
    "helm_validate_values",
    "helm_validate_manifests",
    "helm_get_installation_plan",
    "kubernetes_get_cluster_info",
}


@pytest.mark.asyncio
async def test_write_enabled_server_registers_exact_13_tools_and_zero_prompts(
    bootstrapped_mcp: Any,
) -> None:
    """When allow_write=True, FastMCP must expose the exact 13 tools, <=8 params per tool, and 0 prompts."""
    async with Client(bootstrapped_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        assert tool_names == EXPECTED_ALL_TOOLS
        assert len(tools) == 13
        assert tool_names.isdisjoint(DELETED_LEGACY_TOOLS)

        for tool in tools:
            assert tool.description and len(tool.description.strip()) > 20
            props = (tool.inputSchema or {}).get("properties", {})
            assert len(props) <= 8, f"Tool '{tool.name}' has {len(props)} parameters (> 8 limit)"

        prompts = await client.list_prompts()
        assert prompts == []


@pytest.mark.asyncio
async def test_readonly_server_hides_mutate_tools(readonly_mcp: Any) -> None:
    """When allow_write=False (default), FastMCP must hide all 5 mutate tools and expose only 8 tools."""
    async with Client(readonly_mcp) as client:
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}

        assert tool_names == EXPECTED_READ_AND_SESSION_TOOLS
        assert len(tools) == 8
        assert tool_names.isdisjoint(EXPECTED_MUTATE_TOOLS)


@pytest.mark.asyncio
async def test_discovery_and_inspection_tools_via_client(bootstrapped_mcp: Any) -> None:
    """Test helm_search_charts, helm_list_releases, and helm_get_release_status over the MCP wire."""
    async with Client(bootstrapped_mcp) as client:
        # 1. helm_search_charts
        search_res = await client.call_tool(
            "helm_search_charts",
            {"query": "postgresql", "repository": "bitnami", "limit": 5},
        )
        search_data = json.loads(get_text(search_res))
        assert len(search_data) == 2
        assert search_data[0]["name"] == "bitnami/postgresql"

        # 2. helm_list_releases
        list_res = await client.call_tool(
            "helm_list_releases",
            {"namespace": "prod", "status": "deployed"},
        )
        list_data = json.loads(get_text(list_res))
        assert list_data["count"] == 1
        assert list_data["releases"][0]["name"] == "my-postgres"

        # 3. helm_get_release_status
        status_res = await client.call_tool(
            "helm_get_release_status",
            {"release_name": "my-postgres", "namespace": "prod"},
        )
        status_data = json.loads(get_text(status_res))
        assert status_data["status"] == "deployed"
        assert status_data["resource_uris"]["values"] == "helm://releases/prod/my-postgres/values"


@pytest.mark.asyncio
async def test_render_manifests_and_plan_release_with_json_coercion_via_client(
    bootstrapped_mcp: Any,
) -> None:
    """Test helm_render_manifests and helm_plan_release, including stringified JSON values coercion."""
    async with Client(bootstrapped_mcp) as client:
        # Pass values as a stringified JSON object to verify JsonCoercionMiddleware on the wire
        render_res = await client.call_tool(
            "helm_render_manifests",
            {
                "chart_ref": "bitnami/postgresql",
                "namespace": "prod",
                "values": '{"image": {"tag": "16.5.0"}}',
                "include_full": True,
            },
        )
        render_data = json.loads(get_text(render_res))
        assert render_data["summary"]["secrets_redacted"] is True
        assert "***REDACTED***" in render_data["full_manifests"]
        assert "16.5.0" in render_data["full_manifests"]

        # Plan release against existing prod/my-postgres
        plan_res = await client.call_tool(
            "helm_plan_release",
            {
                "chart_ref": "bitnami/postgresql",
                "release_name": "my-postgres",
                "namespace": "prod",
                "values": {"image": {"tag": "16.5.0"}, "replicas": 2},
            },
        )
        plan_data = json.loads(get_text(plan_res))
        assert plan_data["mode"] == "upgrade"
        assert len(plan_data["diff"]["image_changes"]) == 1
        assert len(plan_data["diff"]["replica_changes"]) == 1


@pytest.mark.asyncio
async def test_mutating_tools_and_cluster_tools_via_client(bootstrapped_mcp: Any) -> None:
    """Test helm_ensure_repository, helm_install_chart, helm_upgrade_release, helm_rollback_release, helm_uninstall_release, kubernetes_check_prerequisites, and kubernetes_set_context."""
    async with Client(bootstrapped_mcp) as client:
        # 1. helm_ensure_repository
        repo_res = await client.call_tool(
            "helm_ensure_repository",
            {"repo_name": "jetstack", "repo_url": "https://charts.jetstack.io"},
        )
        assert json.loads(get_text(repo_res))["added"] is True

        # 2. kubernetes_check_prerequisites (with stringified list to test coercion)
        prereq_res = await client.call_tool(
            "kubernetes_check_prerequisites",
            {
                "min_kubernetes_version": "1.25.0",
                "required_api_resources": '["Deployment", "Service", "Certificate"]',
            },
        )
        prereq_data = json.loads(get_text(prereq_res))
        assert prereq_data["all_prerequisites_met"] is True

        # 3. kubernetes_set_context
        ctx_res = await client.call_tool(
            "kubernetes_set_context",
            {"context_name": "prod-cluster"},
        )
        assert json.loads(get_text(ctx_res))["context_name"] == "prod-cluster"

        # 4. helm_install_chart
        install_res = await client.call_tool(
            "helm_install_chart",
            {
                "chart_ref": "bitnami/postgresql",
                "release_name": "orders-db",
                "namespace": "prod",
                "create_namespace": True,
            },
        )
        assert json.loads(get_text(install_res))["status"] == "deployed"

        # 5. helm_upgrade_release
        up_res = await client.call_tool(
            "helm_upgrade_release",
            {
                "release_name": "orders-db",
                "chart_ref": "bitnami/postgresql",
                "namespace": "prod",
                "values_strategy": "reuse",
            },
        )
        assert json.loads(get_text(up_res))["status"] == "deployed"

        # 6. helm_rollback_release
        rb_res = await client.call_tool(
            "helm_rollback_release",
            {"release_name": "orders-db", "namespace": "prod", "revision": 1},
        )
        assert json.loads(get_text(rb_res))["status"] == "rolled_back"

        # 7. helm_uninstall_release
        un_res = await client.call_tool(
            "helm_uninstall_release",
            {"release_name": "orders-db", "namespace": "prod"},
        )
        assert json.loads(get_text(un_res))["status"] == "uninstalled"


@pytest.mark.asyncio
async def test_tool_error_handling_for_bare_chart_name_and_missing_release(
    bootstrapped_mcp: Any,
) -> None:
    """Calling tools with bare chart_ref or missing release should raise clean ToolError with model guidance."""
    async with Client(bootstrapped_mcp) as client:
        with pytest.raises(ToolError, match="helm_search_charts"):
            await client.call_tool(
                "helm_install_chart",
                {"chart_ref": "postgresql", "release_name": "bad-install", "namespace": "prod"},
            )

        with pytest.raises(ToolError, match="helm_list_releases"):
            await client.call_tool(
                "helm_get_release_status",
                {"release_name": "nonexistent-release", "namespace": "prod"},
            )
