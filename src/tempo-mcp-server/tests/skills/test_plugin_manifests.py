"""Conformance tests for plugin.json and mcp.json under Agent Plugins v1.0.0."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_plugin_json_valid():
    plugin_path = PROJECT_ROOT / "plugin.json"
    assert plugin_path.is_file(), "plugin.json missing at project root"
    plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert plugin["$schema"] == "https://agentplugins.io/schema/v1.0.0/plugin.json"
    assert plugin["name"] == "tempo"
    assert plugin["version"]
    assert plugin["description"]
    assert "com.anysphere.cursor" not in plugin.get("extensions", {})
    assert not (PROJECT_ROOT / "com.anysphere.cursor").exists()


def test_mcp_json_valid():
    mcp_path = PROJECT_ROOT / "mcp.json"
    assert mcp_path.is_file(), "mcp.json missing at project root"
    mcp_cfg = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert mcp_cfg["$schema"] == "https://agentplugins.io/schema/v1.0.0/mcp.json"
    srv = mcp_cfg["mcpServers"]["tempo"]
    assert srv["command"] == "uv"
    assert "--read-only" in srv["args"]
    assert srv["env"]["MCP_ALLOW_WRITE"] == "false"
