"""Integration tests for MCP protocol surface: tools, resources, prompts, parameter limits, and toolset filtering."""

import pytest
from fastmcp import Client

from tempo_mcp_server.config import Config
from tempo_mcp_server.server.bootstrap import ServerBootstrap


class TestMcpProtocolSurface:
    """Verify tool counts, resource URIs, zero prompts, and <= 8 parameters per tool."""

    @pytest.mark.asyncio
    async def test_read_only_default_registers_16_tools_and_zero_prompts(self):
        cfg = Config.from_cli_and_env(["--read-only", "--toolsets", "all"])
        mcp, _, _ = ServerBootstrap.build(cfg)
        async with Client(mcp) as client:
            tools = await client.list_tools()
            prompts = await client.list_prompts()
            resources = await client.list_resources()
            templates = await client.list_resource_templates()

            tool_names = {t.name for t in tools}
            assert len(tool_names) == 16
            assert "tempo_patch_tenant_overrides" not in tool_names
            assert "tempo_apply_operator_cr" not in tool_names
            assert "tempo_query_a2ui" in tool_names
            assert "tempo_compare_span_cohorts" in tool_names
            assert "tempo_analyze_service_red" in tool_names
            assert prompts == []
            assert len(resources) + len(templates) == 10

    @pytest.mark.asyncio
    async def test_allow_write_registers_all_18_tools_and_enforces_param_limit(self):
        cfg = Config.from_cli_and_env(["--allow-write", "--toolsets", "all"])
        mcp, _, _ = ServerBootstrap.build(cfg)
        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert len(tool_names) == 18
            assert "tempo_patch_tenant_overrides" in tool_names
            assert "tempo_apply_operator_cr" in tool_names

            for tool in tools:
                props = (tool.inputSchema or {}).get("properties", {})
                assert len(props) <= 8, (
                    f"Tool {tool.name} has {len(props)} parameters (>8): {list(props.keys())}"
                )

    @pytest.mark.asyncio
    async def test_toolset_filtering_metrics_only(self):
        cfg = Config.from_cli_and_env(["--read-only", "--toolsets", "metrics"])
        mcp, _, _ = ServerBootstrap.build(cfg)
        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == {
                "tempo_traceql_metrics_range",
                "tempo_traceql_metrics_instant",
                "tempo_analyze_service_red",
                "tempo_compare_span_cohorts",
            }
