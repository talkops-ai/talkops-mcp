"""Skill & Plugin contract tests for plugin.json and mcp.json v1.0.0 schema compliance (T-S1)."""

import json
import re
from pathlib import Path

ALLOWED_PLUGIN_JSON_KEYS = {
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


def test_plugin_json_closed_v1_schema(server_root: Path):
    plugin_path = server_root / "plugin.json"
    assert plugin_path.exists(), "plugin.json must exist at server root"

    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    extra_keys = set(data.keys()) - ALLOWED_PLUGIN_JSON_KEYS
    assert not extra_keys, f"plugin.json contains non-v1.0.0 keys: {extra_keys}"

    assert data["$schema"] == "https://agentplugins.io/schema/v1.0.0/plugin.json"
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", data["name"])
    assert re.match(r"^\d+\.\d+\.\d+$", data["version"])
    assert "skills" not in data
    assert "mcpServers" not in data
    assert "keywords" not in data
    assert "com.anysphere.cursor" not in data.get("extensions", {})
    assert not (server_root / "com.anysphere.cursor").exists()


def test_mcp_json_schema_and_multi_cluster_entries(server_root: Path):
    mcp_path = server_root / "mcp.json"
    assert mcp_path.exists(), "mcp.json must exist at server root"

    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert data["$schema"] == "https://agentplugins.io/schema/v1.0.0/mcp.json"
    servers = data.get("mcpServers", {})
    assert "argo-rollout" in servers
    assert len(servers) >= 2, "mcp.json should include default and multi-cluster server entries"

    for name, cfg in servers.items():
        assert cfg.get("type") in ("stdio", "http"), f"Server '{name}' must specify explicit type"
        env = cfg.get("env", {})
        assert env.get("MCP_ALLOW_WRITE") == "false", (
            f"Server '{name}' in mcp.json must default MCP_ALLOW_WRITE to 'false'"
        )
