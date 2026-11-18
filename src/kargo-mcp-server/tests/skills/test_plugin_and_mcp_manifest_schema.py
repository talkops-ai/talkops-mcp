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
    assert data["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert re.fullmatch(r"[a-z0-9-]+", data["name"])
    assert data["name"] == "kargo"
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"])
    assert "com.anysphere.cursor" not in (data.get("extensions") or {})
    assert not (server_root / "com.anysphere.cursor").exists()



def test_all_5_skill_directories_exist(server_root: Path) -> None:
    skills_dir = server_root / "skills"
    found = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    assert found == EXPECTED_SKILL_DIRS


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
    assert list(data["mcpServers"]) == ["kargo"]
    entry = data["mcpServers"]["kargo"]
    cli = next(iter(project["scripts"]))
    assert entry["type"] == "stdio"
    assert entry["command"] == "uvx"
    assert entry["args"] == ["--from", f"{project['name']}=={project['version']}", cli, "--transport", "stdio"]
    assert entry["env"]["MCP_ALLOW_WRITE"] == "false"
    # Agent Plugins 1.0.0 only expands ${PLUGIN_ROOT} and ${PLUGIN_DATA} in portable configs.
    assert not _re.search(r"\$\{(?!PLUGIN_ROOT\}|PLUGIN_DATA\})", _json.dumps(entry))
