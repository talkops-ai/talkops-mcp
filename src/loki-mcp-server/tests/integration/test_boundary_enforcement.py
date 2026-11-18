"""Integration tests for Skill & Execution Layer separation boundaries.

Verifies:
- 14 read-only loki_* tools registered by default (allow_write=False)
- 18 total loki_* tools registered when allow_write=True
- Every tool name starts with 'loki_' (zero unprefixed legacy tools)
- Every tool has <= 8 parameters
- Every tool description is concise (<= 60 words)
- Every tool declares accurate ToolAnnotations (readOnlyHint, destructiveHint, title)
- LOKI_MCP_INSTRUCTIONS.md is <= 45 lines and contains no workflow/runbook sections
- Zero server-bound MCP prompts registered
- Zero static markdown reference resources registered
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import Client

from loki_mcp_server.server.bootstrap import ServerBootstrap
from tests.conftest import LOKI_BASE_URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSTRUCTIONS_PATH = (
    PROJECT_ROOT / "loki_mcp_server" / "static" / "LOKI_MCP_INSTRUCTIONS.md"
)

EXPECTED_READ_TOOLS = {
    "loki_get_labels",
    "loki_get_label_values",
    "loki_get_series",
    "loki_get_log_patterns",
    "loki_get_detected_fields",
    "loki_get_query_stats",
    "loki_query_instant",
    "loki_query_range",
    "loki_query_a2ui",
    "loki_summarize_service_logs",
    "loki_compare_periods",
    "loki_correlate_trace_logs",
    "loki_analyze_volume",
    "loki_get_diagnostics",
}

EXPECTED_WRITE_TOOLS = {
    "loki_upsert_rule_group",
    "loki_delete_rule_group",
    "loki_manage_delete_requests",
    "loki_apply_operator_cr",
}

DESTRUCTIVE_TOOLS = {
    "loki_delete_rule_group",
    "loki_manage_delete_requests",
}


class TestBoundaryEnforcement:
    """Enforces architectural invariants of the refactored Loki MCP execution plane."""

    @pytest.mark.asyncio
    async def test_default_read_only_registers_14_tools(self, mock_loki_http):
        env = {
            "LOKI_URL": LOKI_BASE_URL,
            "MCP_ALLOW_WRITE": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            mcp, _, _ = ServerBootstrap.initialize(["--read-only"])
            async with Client(transport=mcp) as client:
                tools = await client.list_tools()
                names = {t.name for t in tools}
                assert names == EXPECTED_READ_TOOLS
                assert len(names) == 14

    @pytest.mark.asyncio
    async def test_allow_write_registers_all_18_tools(self, mock_loki_http):
        env = {
            "LOKI_URL": LOKI_BASE_URL,
            "MCP_ALLOW_WRITE": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            mcp, _, _ = ServerBootstrap.initialize(["--allow-write"])
            async with Client(transport=mcp) as client:
                tools = await client.list_tools()
                names = {t.name for t in tools}
                assert names == (EXPECTED_READ_TOOLS | EXPECTED_WRITE_TOOLS)
                assert len(names) == 18

    @pytest.mark.asyncio
    async def test_all_tools_have_loki_prefix_parameter_cap_annotations_and_concise_descriptions(
        self, mock_loki_http
    ):
        mcp, _, _ = ServerBootstrap.initialize(["--allow-write"])
        async with Client(transport=mcp) as client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.name.startswith("loki_"), (
                    f"Tool '{tool.name}' must start with 'loki_' prefix"
                )
                props = (tool.inputSchema or {}).get("properties", {})
                assert len(props) <= 8, (
                    f"Tool '{tool.name}' has {len(props)} parameters (> 8 max): {list(props.keys())}"
                )

                desc = (tool.description or "").strip()
                word_count = len(desc.split())
                assert word_count <= 60, (
                    f"Tool '{tool.name}' description has {word_count} words (> 60 max): {desc!r}"
                )

                ann = tool.annotations
                assert ann is not None, f"Tool '{tool.name}' is missing ToolAnnotations"
                assert ann.title, f"Tool '{tool.name}' is missing ToolAnnotations.title"
                if tool.name in EXPECTED_READ_TOOLS:
                    assert ann.readOnlyHint is True, (
                        f"Read tool '{tool.name}' must set readOnlyHint=True"
                    )
                    assert ann.destructiveHint is False
                else:
                    assert ann.readOnlyHint is False, (
                        f"Write tool '{tool.name}' must set readOnlyHint=False"
                    )
                    if tool.name in DESTRUCTIVE_TOOLS:
                        assert ann.destructiveHint is True
                    else:
                        assert ann.destructiveHint is False

    def test_loki_mcp_instructions_is_concise_and_free_of_runbooks(self):
        text = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 45, (
            f"LOKI_MCP_INSTRUCTIONS.md has {len(lines)} lines (> 45 max)"
        )
        for forbidden in ("workflow", "runbook", "decision tree", "threshold"):
            assert forbidden not in text.lower(), (
                f"LOKI_MCP_INSTRUCTIONS.md must not contain procedural '{forbidden}' sections"
            )

    @pytest.mark.asyncio
    async def test_zero_prompts_registered(self, mcp_client):
        prompts = await mcp_client.list_prompts()
        assert len(prompts) == 0, f"Expected 0 server-bound prompts, found: {prompts}"

    @pytest.mark.asyncio
    async def test_nine_dynamic_resources_registered(self, mcp_client):
        resources = await mcp_client.list_resources()
        templates = await mcp_client.list_resource_templates()
        static_uris = {str(r.uri) for r in resources}
        template_uris = {str(t.uriTemplate) for t in templates}
        all_uris = static_uris | template_uris

        expected_uris = {
            "loki://server/capabilities",
            "loki://system/health",
            "loki://schema/labels",
            "loki://config/guardrails",
            "loki://config/backends",
            "loki://rules/groups",
            "loki://compactor/delete-requests",
            "loki://operator/crs/{namespace}",
            "loki://operator/manifests/{kind}/{namespace}/{name}",
        }
        assert all_uris == expected_uris
