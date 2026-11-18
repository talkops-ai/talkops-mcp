"""Contract tests for plugin.json and mcp.json packaging."""

from __future__ import annotations

import json
import re
from pathlib import Path

EXPECTED_SKILL_DIRS = {
    "onboarding-kargo-pipelines",
    "promoting-and-approving-freight",
    "rolling-back-kargo-stages",
    "troubleshooting-kargo-pipelines",
    "managing-kargo-credentials-and-access",
}

ALLOWED_PLUGIN_KEYS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "extensions",
}


def test_plugin_json_adheres_to_closed_v1_schema(server_root: Path) -> None:
    plugin_path = server_root / "plugin.json"
    assert plugin_path.is_file(), "plugin.json must exist at repository root"

    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert set(data.keys()) <= ALLOWED_PLUGIN_KEYS
    assert data["$schema"] == "https://agentplugins.io/schema/v1.0.0/plugin.json"
    assert re.fullmatch(r"[a-z0-9-]+", data["name"])
    assert data["name"] == "kargo"
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"])
    assert "com.anysphere.cursor" not in (data.get("extensions") or {})
    assert not (server_root / "com.anysphere.cursor").exists()


def test_mcp_json_defines_multi_environment_read_only_servers(
    server_root: Path,
) -> None:
    mcp_path = server_root / "mcp.json"
    assert mcp_path.is_file(), "mcp.json must exist at repository root"

    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert data["$schema"] == "https://agentplugins.io/schema/v1.0.0/mcp.json"
    servers = data.get("mcpServers") or {}
    assert "kargo" in servers
    assert len(servers) >= 2

    for name, entry in servers.items():
        assert entry["type"] == "stdio", f"Server '{name}' must use stdio transport"
        assert "--read-only" in entry["args"]
        assert entry["env"]["MCP_ALLOW_WRITE"] == "false"


def test_all_5_skill_directories_exist(server_root: Path) -> None:
    skills_dir = server_root / "skills"
    found = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    assert found == EXPECTED_SKILL_DIRS
