"""Unit tests for Config CLI flags, environment variables, toolsets, and write gates (T-U3)."""

import pytest
from argo_rollout_mcp_server.config import Config, ServerConfig


def test_default_config_is_read_only(monkeypatch):
    monkeypatch.delenv("MCP_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)
    monkeypatch.delenv("MCP_TOOLSETS", raising=False)

    cfg = Config.from_env()
    assert cfg.allow_write is False
    assert cfg.toolsets == ["all"]
    assert cfg.namespace is None


def test_env_allow_write_and_toolsets(monkeypatch):
    monkeypatch.setenv("MCP_ALLOW_WRITE", "true")
    monkeypatch.setenv("MCP_TOOLSETS", "rollouts,diagnostics")
    monkeypatch.setenv("MCP_NAMESPACE", "production")

    cfg = Config.from_env()
    assert cfg.allow_write is True
    assert cfg.toolsets == ["rollouts", "diagnostics"]
    assert cfg.namespace == "production"


def test_env_read_only_overrides_allow_write(monkeypatch):
    monkeypatch.setenv("MCP_ALLOW_WRITE", "true")
    monkeypatch.setenv("MCP_READ_ONLY", "true")

    cfg = Config.from_env()
    assert cfg.allow_write is False


def test_cli_flags_override_env(monkeypatch):
    monkeypatch.setenv("MCP_ALLOW_WRITE", "false")
    cfg = Config.from_cli_and_env(
        [
            "--allow-write",
            "--toolsets",
            "migration,analysis",
            "--prometheus-url",
            "http://prom.monitoring:9090",
            "--context",
            "eu-central-1",
            "--transport",
            "http",
            "--port",
            "9099",
        ]
    )
    assert cfg.allow_write is True
    assert cfg.toolsets == ["migration", "analysis"]
    assert cfg.prometheus_url == "http://prom.monitoring:9090"
    assert cfg.kubernetes.context_name == "eu-central-1"
    assert cfg.transport == "http"
    assert cfg.port == 9099


def test_cli_read_only_overrides_cli_allow_write():
    cfg = Config.from_cli_and_env(["--allow-write", "--read-only"])
    assert cfg.allow_write is False


def test_invalid_toolset_raises_value_error():
    with pytest.raises(ValueError, match="Unknown toolset"):
        ServerConfig(toolsets=["nonexistent_toolset"])
