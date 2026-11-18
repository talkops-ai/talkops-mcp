"""Integration tests enforcing architectural boundaries, tool schema caps, and bounded context."""

from __future__ import annotations

import pytest

from prometheus_mcp_server.config import ServerConfig
from prometheus_mcp_server.server.bootstrap import ServerBootstrap

WRITE_OR_DESTRUCTIVE_TOOLS = {
    "prom_upsert_rule_group",
    "prom_delete_rule_group",
    "prom_apply_scrape_config",
    "prom_delete_scrape_config",
    "prom_install_exporter",
    "prom_uninstall_exporter",
}

DESTRUCTIVE_TOOLS = {
    "prom_delete_rule_group",
    "prom_delete_scrape_config",
    "prom_uninstall_exporter",
}


class TestBoundaryEnforcement:
    @pytest.mark.asyncio
    async def test_tool_ceiling_parameter_cap_and_annotations(self) -> None:
        mcp, _ = ServerBootstrap.initialize(config=ServerConfig(allow_write=True))
        tools = await mcp.list_tools()

        # 1. Tool count ceiling: <= 20 tools (exact: 19)
        assert len(tools) == 19, f"Expected 19 tools, got {len(tools)}"

        for tool in tools:
            # 2. Parameter count cap: <= 8 parameters per tool
            schema = getattr(tool, "parameters", None) or getattr(tool, "inputSchema", None) or {}
            props = schema.get("properties", {})
            # Exclude fastmcp injected ctx if present
            user_params = [k for k in props.keys() if k != "ctx"]
            assert len(user_params) <= 8, (
                f"Tool '{tool.name}' has {len(user_params)} parameters (exceeds <= 8 cap): {user_params}"
            )

            # 3. Honest ToolAnnotations on every single tool
            ann = tool.annotations
            assert ann is not None, f"Tool '{tool.name}' is missing ToolAnnotations"
            assert ann.title, f"Tool '{tool.name}' is missing ToolAnnotations.title"

            if tool.name in WRITE_OR_DESTRUCTIVE_TOOLS:
                assert ann.readOnlyHint is False, (
                    f"Mutating tool '{tool.name}' must have readOnlyHint=False"
                )
            else:
                assert ann.readOnlyHint is True, (
                    f"Read-only tool '{tool.name}' must have readOnlyHint=True"
                )

            if tool.name in DESTRUCTIVE_TOOLS:
                assert ann.destructiveHint is True, (
                    f"Destructive tool '{tool.name}' must have destructiveHint=True"
                )
            else:
                assert ann.destructiveHint is False, (
                    f"Non-destructive tool '{tool.name}' must have destructiveHint=False"
                )

    @pytest.mark.asyncio
    async def test_zero_alertmanager_bounded_context_overlap(self) -> None:
        mcp, _ = ServerBootstrap.initialize(config=ServerConfig(allow_write=True))
        tools = await mcp.list_tools()
        resources = await mcp.list_resources()
        templates = await mcp.list_resource_templates()

        for t in tools:
            assert not t.name.startswith("am_"), (
                f"Alertmanager tool '{t.name}' must not be registered on prometheus-mcp-server"
            )
            assert "silence" not in t.name.lower(), (
                f"Silence management tool '{t.name}' belongs to alertmanager-mcp-server"
            )

        all_uris = [str(r.uri) for r in resources] + [
            str(t.uri_template) for t in templates
        ]
        for uri in all_uris:
            assert uri.startswith("prom://"), f"Unexpected non-prom URI: {uri}"
            assert "alertmanager" not in uri.lower()
            assert "silence" not in uri.lower()
            # Static doc resources must not be registered on the execution server
            assert uri not in (
                "prom://best-practices",
                "prom://onboarding-guide",
                "prom://exporters/catalog",
            )
