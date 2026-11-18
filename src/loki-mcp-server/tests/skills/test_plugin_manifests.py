"""Tests for Agent Plugins v1.0.0 manifests (plugin.json and mcp.json)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
PLUGIN_JSON = ROOT_DIR / "plugin.json"
MCP_JSON = ROOT_DIR / "mcp.json"

CLOSED_V1_PLUGIN_FIELDS = {
    "$schema",
    "name",
    "version",
    "displayName",
    "description",
    "author",
    "license",
    "keywords",
    "repository",
    "homepage",
    "extensions",
}


class TestPluginManifests:
    """Validate Agent Plugins v1.0.0 packaging manifests."""

    def test_plugin_json_follows_closed_v1_schema(self):
        assert PLUGIN_JSON.exists(), "plugin.json must exist at package root"
        data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))

        assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        assert data["name"] == "talkops-loki"
        assert data["version"] == "0.2.0"

        unexpected_keys = set(data.keys()) - CLOSED_V1_PLUGIN_FIELDS
        assert not unexpected_keys, (
            f"plugin.json contains non-v1.0.0 fields (closed schema): {unexpected_keys}"
        )
        assert "com.anysphere.cursor" not in data.get("extensions", {})
        assert not (ROOT_DIR / "com.anysphere.cursor").exists()

    def test_mcp_json_is_valid_and_read_only_by_default(self):
        assert MCP_JSON.exists(), "mcp.json must exist at package root"
        data = json.loads(MCP_JSON.read_text(encoding="utf-8"))

        assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
        assert "loki" in data["mcpServers"]
        loki_srv = data["mcpServers"]["loki"]
        assert loki_srv["type"] == "stdio"
        assert loki_srv["command"] == "loki-mcp-server"
        assert loki_srv["cwd"] == "./"
        assert loki_srv["env"]["MCP_ALLOW_WRITE"] == "false"
