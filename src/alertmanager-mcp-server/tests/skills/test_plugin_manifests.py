"""Strict Agent Plugins v1.0.0 manifest validation tests for root `plugin.json` and `mcp.json`."""

from __future__ import annotations

import json
import re
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[2]
PLUGIN_JSON = PLUGIN_DIR / "plugin.json"
MCP_JSON = PLUGIN_DIR / "mcp.json"

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
    assert list(data["mcpServers"]) == ["alertmanager"]
    entry = data["mcpServers"]["alertmanager"]
    cli = next(iter(project["scripts"]))
    assert entry["type"] == "stdio"
    assert entry["command"] == "uvx"
    assert entry["args"] == ["--from", f"{project['name']}=={project['version']}", cli, "--transport", "stdio"]
    assert entry["env"]["MCP_ALLOW_WRITE"] == "false"
    # Agent Plugins 1.0.0 only expands ${PLUGIN_ROOT} and ${PLUGIN_DATA} in portable configs.
    assert not _re.search(r"\$\{(?!PLUGIN_ROOT\}|PLUGIN_DATA\})", _json.dumps(entry))
