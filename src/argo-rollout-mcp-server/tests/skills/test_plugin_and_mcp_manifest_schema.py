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

    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", data["name"])
    assert re.match(r"^\d+\.\d+\.\d+$", data["version"])
    assert "skills" not in data
    assert "mcpServers" not in data
    assert "keywords" not in data
    assert "com.anysphere.cursor" not in data.get("extensions", {})
    assert not (server_root / "com.anysphere.cursor").exists()


def test_mcp_json_launches_pinned_pypi_release_read_only() -> None:
    """mcp.json runs this package's exact PyPI release over stdio, read-only, with only portable variables."""
    import json as _json
    import re as _re
    import tomllib as _tomllib
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[2]
    project = _tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    data = _json.loads((root / "mcp.json").read_text(encoding="utf-8"))

    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    assert list(data["mcpServers"]) == ["argo-rollout"]
    entry = data["mcpServers"]["argo-rollout"]
    cli = next(iter(project["scripts"]))
    assert entry["type"] == "stdio"
    assert entry["command"] == "uvx"
    assert entry["args"] == ["--from", f"{project['name']}=={project['version']}", cli, "--transport", "stdio"]
    assert entry["env"]["MCP_ALLOW_WRITE"] == "false"
    # Agent Plugins 1.0.0 only expands ${PLUGIN_ROOT} and ${PLUGIN_DATA} in portable configs.
    assert not _re.search(r"\$\{(?!PLUGIN_ROOT\}|PLUGIN_DATA\})", _json.dumps(entry))
