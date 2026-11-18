"""Contract tests verifying every tool referenced in SKILL.md exists on the FastMCP server."""

import re
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client

from tests.skills.test_skill_spec_compliance import (
    EXPECTED_SKILLS,
    SKILLS_DIR,
    _parse_frontmatter,
)


@pytest.mark.asyncio
async def test_skill_allowed_tools_and_inline_references_match_mcp_server(
    mcp_server_write: Any,
) -> None:
    """Every tool in allowed-tools and every tool call mentioned in SKILL.md must exist on the MCP server."""
    async with Client(mcp_server_write) as client:
        registered_tools = {t.name for t in await client.list_tools()}

    # Deprecated/removed v0.3.0 tool names that must NEVER appear in any SKILL.md
    removed_legacy_tools = {
        "rollback_to_revision",
        "validate_application_config",
        "generate_application_manifest",
        "create_applicationset_manifest",
        "onboard_repository_https",
        "onboard_repository_ssh",
        "generate_repository_secret_manifest",
    }

    for skill_name in EXPECTED_SKILLS:
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        fm = _parse_frontmatter(skill_md)

        allowed = fm.get("allowed-tools", [])
        assert len(allowed) > 0, f"{skill_name} must declare allowed-tools in frontmatter"

        for tool_name in allowed:
            assert tool_name in registered_tools, (
                f"Skill '{skill_name}' lists unknown tool '{tool_name}' in allowed-tools"
            )

        for legacy in removed_legacy_tools:
            assert legacy not in content, (
                f"Skill '{skill_name}' references removed v0.3.0 tool '{legacy}'"
            )

        # Check any function-style invocation `tool_name(` in SKILL.md
        called_names = set(re.findall(r"`([a-z]+_[a-z_]+)\(", content))
        for called in called_names:
            assert called in registered_tools, (
                f"Skill '{skill_name}' invokes '{called}(...)' which is not a registered MCP tool"
            )
