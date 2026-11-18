"""Contract tests for root plugin.json and mcp.json (Agent Plugins v1.0.0)."""

import json
import re
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent.parent.parent

ALLOWED_PLUGIN_TOP_LEVEL_KEYS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "license",
    "homepage",
    "repository",
    "extensions",
}


def test_plugin_json_valid_and_paths_resolve() -> None:
    """Verify plugin.json conforms strictly to closed Agent Plugins v1.0.0 schema."""
    plugin_json_path = PLUGIN_DIR / "plugin.json"
    assert plugin_json_path.exists()

    data = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    unknown_keys = set(data.keys()) - ALLOWED_PLUGIN_TOP_LEVEL_KEYS
    assert not unknown_keys, (
        f"plugin.json contains non-standard top-level keys {unknown_keys} "
        f"(allowed: {sorted(ALLOWED_PLUGIN_TOP_LEVEL_KEYS)})"
    )

    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert data["name"] == "argocd-gitops-plugin"
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", data["name"])
    assert data["version"] == "0.4.1"
    assert isinstance(data["author"], dict)
    assert "name" in data["author"]

    ext = data["extensions"]["com.talkops"]
    mcp_ref = PLUGIN_DIR / ext["mcpServers"]
    assert mcp_ref.exists(), f"Missing MCP config referenced by plugin.json: {mcp_ref}"

    skills = ext["skills"]
    assert len(skills) == 4
    for rel_skill in skills:
        skill_path = PLUGIN_DIR / rel_skill
        assert skill_path.is_dir(), f"Missing skill directory: {skill_path}"
        assert (skill_path / "SKILL.md").exists(), f"Missing SKILL.md in {skill_path}"


def test_mcp_json_uses_safe_defaults() -> None:
    """Verify mcp.json conforms to Agent Plugins v1.0.0 and uses safe read-only defaults."""
    mcp_json_path = PLUGIN_DIR / "mcp.json"
    assert mcp_json_path.exists()

    data = json.loads(mcp_json_path.read_text(encoding="utf-8"))
    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    server_cfg = data["mcpServers"]["argocd-mcp-server"]
    assert server_cfg["type"] == "stdio"
    assert server_cfg["command"] == "uv"
    assert server_cfg["cwd"] == "./"
    assert "argocd-mcp-server" in server_cfg["args"]
    env = server_cfg["env"]
    assert "MCP_ALLOW_WRITE" in env
    assert "false" in env["MCP_ALLOW_WRITE"]
