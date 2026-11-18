"""Strict Agent Plugins v1.0.0 manifest validation tests for root `plugin.json` and `mcp.json`."""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_JSON = PROJECT_ROOT / "plugin.json"
MCP_JSON = PROJECT_ROOT / "mcp.json"

ALLOWED_PLUGIN_TOP_LEVEL_KEYS = frozenset(
    {
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
)

FORBIDDEN_PLUGIN_KEYS = frozenset(
    {
        "skills",
        "mcpServers",
        "mcp_servers",
        "schema_version",
        "hooks",
        "agents",
        "commands",
        "keywords",
    }
)


class TestPluginManifests:
    def test_plugin_json_conforms_to_closed_v1_schema(self) -> None:
        assert PLUGIN_JSON.exists(), f"Missing {PLUGIN_JSON}"
        data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))

        assert (
            data.get("$schema")
            == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        )
        assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", data.get("name", ""))
        assert len(data["name"]) <= 64

        top_keys = set(data.keys())
        assert not (top_keys & FORBIDDEN_PLUGIN_KEYS), (
            f"Forbidden top-level keys in plugin.json: {top_keys & FORBIDDEN_PLUGIN_KEYS}"
        )
        assert top_keys.issubset(ALLOWED_PLUGIN_TOP_LEVEL_KEYS), (
            f"Unexpected top-level keys in plugin.json: {top_keys - ALLOWED_PLUGIN_TOP_LEVEL_KEYS}"
        )

        if "extensions" in data:
            for ext_key in data["extensions"]:
                assert re.match(
                    r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", ext_key
                ), f"Invalid reverse-DNS extension key: {ext_key}"

    def test_mcp_json_conforms_to_v1_schema(self) -> None:
        assert MCP_JSON.exists(), f"Missing {MCP_JSON}"
        data = json.loads(MCP_JSON.read_text(encoding="utf-8"))

        assert (
            data.get("$schema")
            == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
        )
        servers = data.get("mcpServers")
        assert isinstance(servers, dict) and len(servers) >= 1

        for name, srv in servers.items():
            assert srv.get("type") in ("stdio", "streamable-http", "sse"), (
                f"Server '{name}' must explicitly declare transport 'type'"
            )
            if srv["type"] == "stdio":
                cmd = srv.get("command", "")
                assert cmd and " " not in cmd, (
                    f"Server '{name}' command must be a single executable token"
                )
                cwd = srv.get("cwd", "")
                assert cwd.startswith("./") and ".." not in cwd, (
                    f"Server '{name}' cwd must be plugin-relative starting with './'"
                )
            env = srv.get("env", {})
            assert env.get("MCP_ALLOW_WRITE") == "false", (
                "Default plugin mcp.json must start in safe read-only mode (MCP_ALLOW_WRITE=false)"
            )
            assert "com.anysphere.cursor" not in json.loads(
                PLUGIN_JSON.read_text(encoding="utf-8")
            ).get("extensions", {})
            assert not (PROJECT_ROOT / "com.anysphere.cursor").exists()
