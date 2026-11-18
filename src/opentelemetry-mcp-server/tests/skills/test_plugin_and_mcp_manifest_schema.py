"""T-S1 & T-S2: Validate plugin.json and mcp.json against Agent Plugins v1.0.0."""

from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

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


def test_plugin_json_schema_and_extensions():
    plugin_path = ROOT_DIR / "plugin.json"
    assert plugin_path.exists(), "plugin.json must exist at package root"

    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert data.get("$schema") == "https://agentplugins.io/schema/v1.0.0/plugin.json"
    assert set(data.keys()).issubset(ALLOWED_PLUGIN_KEYS), (
        f"Unexpected top-level keys in plugin.json: {set(data.keys()) - ALLOWED_PLUGIN_KEYS}"
    )
    assert data.get("name") in ("opentelemetry", "opentelemetry-mcp")
    assert data.get("version")
    assert "com.anysphere.cursor" not in data.get("extensions", {})
    assert not (ROOT_DIR / "com.anysphere.cursor").exists()


def test_mcp_json_schema_and_safe_defaults():
    mcp_path = ROOT_DIR / "mcp.json"
    assert mcp_path.exists(), "mcp.json must exist at package root"

    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert data.get("$schema") == "https://agentplugins.io/schema/v1.0.0/mcp.json"

    servers = data.get("mcpServers", {})
    assert {"opentelemetry", "opentelemetry-staging", "opentelemetry-production"}.issubset(
        set(servers.keys())
    )
    for name, entry in servers.items():
        assert entry.get("type") in ("stdio", "http"), (
            f"Server '{name}' must specify type in ('stdio', 'http')"
        )
        env = entry.get("env", {})
        assert env.get("MCP_ALLOW_WRITE") == "false", (
            f"Server '{name}' must default MCP_ALLOW_WRITE to 'false' for safety"
        )
