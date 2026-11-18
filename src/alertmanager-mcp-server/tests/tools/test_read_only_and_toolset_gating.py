"""Tests for read-only mode, toolset gating, parameter count <= 8, and `outputSchema` presence."""

from __future__ import annotations

import pytest

from alertmanager_mcp_server.config import BackendConfig, ServerConfig
from alertmanager_mcp_server.server.bootstrap import ServerBootstrap

MUTATING_TOOLS = {
    "am_create_silence",
    "am_silence_alert",
    "am_update_silence",
    "am_expire_silence",
    "am_push_test_alert",
}

READONLY_TOOLS = {
    "am_summarize_oncall",
    "am_list_alerts",
    "am_list_alert_groups",
    "am_check_notification_health",
    "am_explain_routing",
    "am_list_silences",
    "am_preview_silence",
    "am_audit_alert_hygiene",
    "am_audit_silences",
}


class TestToolSurfaceAndGating:
    @pytest.mark.asyncio
    async def test_all_14_tools_have_at_most_8_params_and_output_schema(
        self, test_server_config: ServerConfig
    ) -> None:
        """Regression test for P3: all 14 tools must have <= 8 params, outputSchema, and 0 legacy prompts."""
        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert len(tools) == 14
        assert tool_names == (READONLY_TOOLS | MUTATING_TOOLS)

        for tool in tools:
            props = (tool.parameters or {}).get("properties", {})
            assert len(props) <= 8, (
                f"Tool '{tool.name}' has {len(props)} parameters (> 8): {list(props.keys())}"
            )
            assert tool.output_schema is not None, (
                f"Tool '{tool.name}' is missing output_schema"
            )

        prompts = await mcp.list_prompts()
        assert len(prompts) == 0
        await service.close()

    @pytest.mark.asyncio
    async def test_read_only_mode_hides_all_5_mutating_tools(
        self, readonly_server_config: ServerConfig
    ) -> None:
        mcp, _, service = ServerBootstrap.initialize(config=readonly_server_config)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert len(tools) == 9
        assert tool_names == READONLY_TOOLS
        assert not (tool_names & MUTATING_TOOLS)
        await service.close()

    @pytest.mark.asyncio
    async def test_toolset_filtering_registers_only_selected_toolsets(
        self, test_backend_config: BackendConfig
    ) -> None:
        cfg = ServerConfig(
            allow_write=True,
            toolsets=["triage", "governance"],
            backends=[test_backend_config],
        )
        mcp, _, service = ServerBootstrap.initialize(config=cfg)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == {
            "am_summarize_oncall",
            "am_list_alerts",
            "am_list_alert_groups",
            "am_audit_alert_hygiene",
            "am_audit_silences",
        }
        await service.close()
