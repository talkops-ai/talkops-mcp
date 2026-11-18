"""Tier-3 conformance tests for Agent Plugins v1.0.0 plugin.json and mcp.json."""

import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def test_plugin_json_conforms_to_agentplugins_v1():
    plugin_path = ROOT_DIR / "plugin.json"
    assert plugin_path.exists()
    data = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert data["name"] == "traefik"
    assert data["version"] == "0.2.1"
    assert "com.anysphere.cursor" not in data.get("extensions", {})
    assert not (ROOT_DIR / "com.anysphere.cursor").exists()


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
    assert list(data["mcpServers"]) == ["traefik"]
    entry = data["mcpServers"]["traefik"]
    cli = next(iter(project["scripts"]))
    assert entry["type"] == "stdio"
    assert entry["command"] == "uvx"
    assert entry["args"] == ["--from", f"{project['name']}=={project['version']}", cli, "--transport", "stdio"]
    assert entry["env"]["MCP_ALLOW_WRITE"] == "false"
    # Agent Plugins 1.0.0 only expands ${PLUGIN_ROOT} and ${PLUGIN_DATA} in portable configs.
    assert not _re.search(r"\$\{(?!PLUGIN_ROOT\}|PLUGIN_DATA\})", _json.dumps(entry))
