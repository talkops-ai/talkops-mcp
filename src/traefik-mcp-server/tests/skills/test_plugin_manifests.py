"""Tier-3 conformance tests for Agent Plugins v1.0.0 plugin.json and mcp.json."""

import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def test_plugin_json_conforms_to_agentplugins_v1():
    plugin_path = ROOT_DIR / "plugin.json"
    assert plugin_path.exists()
    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert data["$schema"] == "https://agentplugins.io/schema/v1.0.0/plugin.json"
    assert data["name"] == "traefik"
    assert data["version"] == "0.2.1"
    assert "com.anysphere.cursor" not in data.get("extensions", {})
    assert not (ROOT_DIR / "com.anysphere.cursor").exists()


def test_mcp_json_conforms_to_stdio_and_safe_defaults():
    mcp_path = ROOT_DIR / "mcp.json"
    assert mcp_path.exists()
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert data["$schema"] == "https://agentplugins.io/schema/v1.0.0/mcp.json"
    servers = data["mcpServers"]
    assert "traefik" in servers
    for s_name, s_cfg in servers.items():
        assert s_cfg["type"] == "stdio", f"{s_name} must use local stdio transport"
        assert "--read-only" in s_cfg["args"]
        assert s_cfg["env"]["MCP_ALLOW_WRITE"] == "false"
        assert s_cfg["env"]["MCP_TRANSPORT"] == "stdio"
