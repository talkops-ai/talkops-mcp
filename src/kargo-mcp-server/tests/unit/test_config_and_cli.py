"""Unit tests for Config defaults, environment variables, and CLI flag parsing."""

from __future__ import annotations

import pytest

from kargo_mcp_server.config import Config


def test_default_config_is_read_only_and_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_TOOLSETS", raising=False)

    cfg = Config.from_env()
    assert cfg.allow_write is False
    assert cfg.transport == "stdio"
    assert cfg.toolsets == ["all"]


def test_env_allow_write_and_read_only_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_ALLOW_WRITE", "true")
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)
    cfg = Config.from_env()
    assert cfg.allow_write is True

    monkeypatch.setenv("MCP_READ_ONLY", "true")
    cfg_ro = Config.from_env()
    assert cfg_ro.allow_write is False


def test_cli_flags_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_ALLOW_WRITE", "false")
    cfg = Config.from_cli_and_env(
        [
            "--allow-write",
            "--transport",
            "streamable-http",
            "--port",
            "9090",
            "--toolsets",
            "pipeline,diagnostics",
            "--kargo-url",
            "https://kargo.example.com:8443",
            "--project",
            "demo",
        ]
    )
    assert cfg.allow_write is True
    assert cfg.transport == "http"
    assert cfg.port == 9090
    assert set(cfg.toolsets) == {"pipeline", "diagnostics"}
    assert cfg.kargo.base_url == "https://kargo.example.com:8443"
    assert cfg.default_project == "demo"


def test_readonly_toolset_forces_allow_write_false() -> None:
    cfg = Config.from_cli_and_env(["--allow-write", "--toolsets", "readonly"])
    assert cfg.allow_write is False


def test_invalid_toolset_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown toolset"):
        Config.from_cli_and_env(["--toolsets", "pipeline,nonexistent"])
