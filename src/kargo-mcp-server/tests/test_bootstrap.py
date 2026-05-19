"""Tests for server bootstrap."""

from unittest.mock import patch, MagicMock

import pytest

from kargo_mcp_server.server.bootstrap import ServerBootstrap


class TestServerBootstrap:
    def test_initialize_creates_server(self):
        """Bootstrap should produce a FastMCP instance and config."""
        mcp, config = ServerBootstrap.initialize()

        assert mcp is not None
        assert config is not None
        assert config.name == "kargo-mcp-server"
        assert mcp._mcp_server.name == "kargo-mcp-server"

    @pytest.mark.asyncio
    async def test_initialize_registers_tools(self):
        """Bootstrap should register all 16 tools."""
        mcp, _ = ServerBootstrap.initialize()
        tools = await mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert len(tool_names) >= 6, f"Expected >=6 tools, got {len(tool_names)}: {tool_names}"

        # Verify key tools are present
        expected_tools = [
            "kargo_project_mgmt",
            "kargo_stage_mgmt",
            "kargo_warehouse_mgmt",
            "kargo_freight_mgmt",
            "kargo_promotion_mgmt",
            "kargo_describe_topology",
        ]
        for tool_name in expected_tools:
            assert tool_name in tool_names, f"Missing tool: {tool_name}"

    @pytest.mark.asyncio
    async def test_initialize_registers_prompts(self):
        """Bootstrap should register all 5 prompts."""
        mcp, _ = ServerBootstrap.initialize()
        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]
        assert len(prompt_names) >= 5, f"Expected >=5 prompts, got {len(prompt_names)}"

        expected_prompts = [
            "kargo-promotion-guided",
            "kargo-pipeline-onboarding-guided",
            "kargo-troubleshoot-guided",
            "kargo-approval-guided",
            "kargo-rollback-guided",
        ]
        for prompt_name in expected_prompts:
            assert prompt_name in prompt_names, f"Missing prompt: {prompt_name}"

    @pytest.mark.asyncio
    async def test_initialize_registers_resources(self):
        """Bootstrap should register resource templates."""
        mcp, _ = ServerBootstrap.initialize()
        resource_templates = await mcp.list_resource_templates()
        # We have parametrized resources (kargo://projects/{name}, etc.)
        assert len(resource_templates) >= 2, f"Expected >=2 resource templates, got {len(resource_templates)}"
