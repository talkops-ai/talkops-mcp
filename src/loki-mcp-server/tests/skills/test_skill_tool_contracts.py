"""Bidirectional contract tests between Agent Skills and the Loki MCP execution plane.

Ensures:
1. Every registered MCP tool (18 loki_* tools) is documented in at least one SKILL.md.
2. Every loki_* tool name mentioned in skills/ exists on the registered MCP server.
3. Every registered loki:// resource (9 resources) is documented in at least one SKILL.md.
4. No SKILL.md, reference file, or tool module references deleted legacy tool names or removed static resources (loki://reference/*).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastmcp import Client

from loki_mcp_server.server.bootstrap import ServerBootstrap

ROOT_DIR = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT_DIR / "skills"
TOOLS_DIR = ROOT_DIR / "loki_mcp_server" / "tools"

TOOL_NAME_RE = re.compile(r"`(loki_[a-z0-9_]+)(?:\([^`]*)?`")
LOKI_URI_RE = re.compile(r"`(loki://[^`\s]+)`")

# Prometheus metric names or config prefixes that start with loki_
KNOWN_NON_TOOL_IDENTIFIERS = frozenset(
    {
        "loki_discarded_samples_total",
        "loki_index_",
    }
)

DELETED_LEGACY_TOOLS = frozenset(
    {
        "get_cluster_labels",
        "get_active_series",
        "get_log_patterns",
        "get_query_stats",
        "execute_logql_instant",
        "execute_logql_query",
    }
)


def _all_skill_markdown() -> str:
    chunks: list[str] = []
    for md_path in sorted(SKILLS_DIR.rglob("*.md")):
        chunks.append(md_path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _skill_entrypoints_markdown() -> str:
    chunks: list[str] = []
    for md_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        chunks.append(md_path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


class TestSkillToolAndResourceContracts:
    """Verifies zero drift between skills/ markdown and the registered FastMCP surface."""

    @pytest.mark.asyncio
    async def test_every_registered_tool_is_referenced_and_valid_in_skills(
        self, mock_loki_http
    ):
        mcp, _, _ = ServerBootstrap.initialize(["--allow-write"])
        async with Client(transport=mcp) as client:
            tools = await client.list_tools()
            registered_tools = {t.name for t in tools}

        assert len(registered_tools) == 18
        entrypoints_text = _skill_entrypoints_markdown()
        all_text = _all_skill_markdown()

        missing_tools = {name for name in registered_tools if name not in entrypoints_text}
        assert not missing_tools, (
            f"Registered MCP tools not referenced in any SKILL.md: {sorted(missing_tools)}"
        )

        # Every backticked loki_* tool name in skills/ must be a registered tool
        referenced_tools = set(TOOL_NAME_RE.findall(all_text)) - KNOWN_NON_TOOL_IDENTIFIERS
        unknown_tools = referenced_tools - registered_tools
        assert not unknown_tools, (
            f"Skills reference unregistered loki_* tool names: {sorted(unknown_tools)}"
        )
        assert referenced_tools == registered_tools

    @pytest.mark.asyncio
    async def test_every_registered_resource_is_referenced_in_skills(self, mock_loki_http):
        mcp, _, _ = ServerBootstrap.initialize(["--allow-write"])
        async with Client(transport=mcp) as client:
            resources = await client.list_resources()
            templates = await client.list_resource_templates()
            registered_uris = {str(r.uri) for r in resources} | {
                str(t.uriTemplate) for t in templates
            }

        assert len(registered_uris) == 9
        entrypoints_text = _skill_entrypoints_markdown()

        missing_uris = {uri for uri in registered_uris if uri not in entrypoints_text}
        assert not missing_uris, (
            f"Registered loki:// resources not referenced in any SKILL.md: {sorted(missing_uris)}"
        )

        all_text = _all_skill_markdown()
        referenced_uris = set(LOKI_URI_RE.findall(all_text))
        unknown_uris = referenced_uris - registered_uris
        assert not unknown_uris, (
            f"Skills reference unregistered or removed loki:// URIs: {sorted(unknown_uris)}"
        )

    def test_zero_deleted_legacy_tool_names_in_skills_or_tools(self) -> None:
        all_skill_text = _all_skill_markdown()
        for legacy in DELETED_LEGACY_TOOLS:
            pattern = re.compile(rf"\b{re.escape(legacy)}\b")
            assert not pattern.search(all_skill_text), (
                f"Legacy unprefixed tool name '{legacy}' still referenced in skills/"
            )

        for py_file in TOOLS_DIR.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for legacy in DELETED_LEGACY_TOOLS:
                pattern = re.compile(rf"\b{re.escape(legacy)}\b")
                assert not pattern.search(content), (
                    f"Legacy unprefixed tool name '{legacy}' found in {py_file.relative_to(ROOT_DIR)}"
                )
