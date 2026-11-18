"""Contract tests verifying 100% alignment between skill docs and registered MCP tools/resources."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from prometheus_mcp_server.config import ServerConfig
from prometheus_mcp_server.server.bootstrap import ServerBootstrap

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"
SERVER_PKG_DIR = PROJECT_ROOT / "prometheus_mcp_server"

TOOL_NAME_RE = re.compile(r"\bprom_[a-z0-9_]+\b")
RESOURCE_URI_RE = re.compile(r"prom://[a-zA-Z0-9_{}/-]+")

DELETED_LEGACY_TOOLS = frozenset(
    {
        "prom_recommend_instrumentation",
        "prom_recommend_exporter",
        "prom_plan_relabel",
        "prom_create_recording_rule",
        "prom_configure_remote_write",
        "prom_draft_alert_rule",
        "prom_tune_alert_rule",
        "prom_suggest_promql",
        "prom_query_a2ui_chart",
        "prom_get_rule_group",
        "prom_describe_alert_rule",
        "prom_validate_promql",
        "prom_explore_labels",
        "prom_test_endpoint",
        "prom_verify_exporter",
        "prom_apply_servicemonitor",
        "prom_delete_servicemonitor",
        "prom_apply_probe",
        "prom_manage_file_sd",
        "prom_optimize_cardinality",
        "prom_check_rule_group",
        "prom_run_rule_tests",
        "prom_simulate_firing_synthetic",
        "prom_simulate_firing_historical",
        "prom_analyze_firing_history",
    }
)


class TestSkillToolAndResourceContracts:
    @pytest.mark.asyncio
    async def test_all_tools_and_resources_referenced_in_skills_exist_on_server(
        self,
    ) -> None:
        mcp, _ = ServerBootstrap.initialize(config=ServerConfig(allow_write=True))
        tools = await mcp.list_tools()
        registered_tools = {t.name for t in tools}

        resources = await mcp.list_resources()
        templates = await mcp.list_resource_templates()
        registered_uris = {str(r.uri) for r in resources} | {
            str(t.uri_template) for t in templates
        }

        md_files = list(SKILLS_DIR.rglob("*.md"))
        assert len(md_files) >= 18

        referenced_tools: set[str] = set()
        for md_path in md_files:
            text = md_path.read_text(encoding="utf-8")
            for match in TOOL_NAME_RE.findall(text):
                referenced_tools.add(match)

            for uri in RESOURCE_URI_RE.findall(text):
                norm_uri = uri.replace("/PrometheusRule/", "/{kind}/")
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
        # Every single one of the 19 MCP tools must be covered across the 6 skills
        assert referenced_tools == registered_tools

    def test_zero_deleted_legacy_tool_names_in_codebase(self) -> None:
        for py_file in SERVER_PKG_DIR.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for legacy_name in DELETED_LEGACY_TOOLS:
                assert legacy_name not in content, (
                    f"Legacy tool name '{legacy_name}' found in {py_file}"
                )
