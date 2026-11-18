"""Contract tests verifying 100% alignment between skill docs and registered MCP tools/resources."""

from __future__ import annotations

import re
from pathlib import Path
import pytest

from alertmanager_mcp_server.server.bootstrap import ServerBootstrap

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"
SERVER_PKG_DIR = PROJECT_ROOT / "alertmanager_mcp_server"

TOOL_NAME_RE = re.compile(r"\bam_[a-z0-9_]+\b")
RESOURCE_URI_RE = re.compile(r"am://[a-zA-Z0-9_{}/-]+")

DELETED_LEGACY_TOOLS = frozenset(
    {
        "am_alert_mgmt",
        "am_silence_mgmt",
        "am_helper_mgmt",
        "am_backend_mgmt",
        "am_list_backends",
        "am_get_backend_status",
        "am_get_routing_tree",
        "am_list_receivers",
        "am_export_config",
        "am_list_recent_changes",
        "am_validate_silence_policy",
        "am_audit_default_route",
    }
)


class TestSkillToolAndResourceContracts:
    @pytest.mark.asyncio
    async def test_all_tools_and_resources_referenced_in_skills_exist_on_server(
        self, test_server_config
    ) -> None:
        mcp, _, service = ServerBootstrap.initialize(config=test_server_config)
        tools = await mcp.list_tools()
        registered_tools = {t.name for t in tools}

        resources = await mcp.list_resources()
        templates = await mcp.list_resource_templates()
        registered_uris = {str(r.uri) for r in resources} | {
            str(t.uri_template) for t in templates
        }

        md_files = list(SKILLS_DIR.rglob("*.md"))
        assert len(md_files) >= 15

        referenced_tools: set[str] = set()
        for md_path in md_files:
            text = md_path.read_text(encoding="utf-8")
            for match in TOOL_NAME_RE.findall(text):
                # Exclude resource internal names like am_backends if ever written,
                # though skills only reference tool names (am_*) and URIs (am://*)
                referenced_tools.add(match)

            for uri in RESOURCE_URI_RE.findall(text):
                # Normalize placeholders like {id} or {sid} to {backend_id}/{silence_id}/{fingerprint}
                norm_uri = (
                    uri.replace("{id}", "{backend_id}")
                    .replace("{sid}", "{silence_id}")
                    .replace("{fp}", "{fingerprint}")
                )
                assert norm_uri in registered_uris, (
                    f"Resource URI '{uri}' in {md_path.relative_to(PROJECT_ROOT)} "
                    f"is not registered on server: {sorted(registered_uris)}"
                )

        assert not (referenced_tools & DELETED_LEGACY_TOOLS), (
            f"Deleted legacy tool names referenced in skills: {referenced_tools & DELETED_LEGACY_TOOLS}"
        )
        missing_tools = referenced_tools - registered_tools
        assert not missing_tools, (
            f"Skills reference unregistered MCP tools: {missing_tools}"
        )
        # All 14 MCP tools should be covered across the 5 operational skills
        assert referenced_tools == registered_tools
        await service.close()

    def test_zero_deleted_legacy_tool_names_in_codebase(self) -> None:
        for py_file in SERVER_PKG_DIR.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for legacy_name in DELETED_LEGACY_TOOLS:
                assert legacy_name not in content, (
                    f"Legacy tool name '{legacy_name}' found in {py_file}"
                )
