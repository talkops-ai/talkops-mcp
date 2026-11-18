"""Unit tests for ServerConfig, Config.from_env(), and CLI argument overrides."""

from __future__ import annotations

import pytest

from helm_mcp_server.config import Config, ServerConfig
from helm_mcp_server.main import apply_cli_overrides


def test_server_config_defaults() -> None:
    """ServerConfig should default to read-only stdio mode with all toolsets."""
    cfg = ServerConfig()
    assert cfg.name == "helm-mcp-server"
    assert cfg.transport == "stdio"
    assert cfg.allow_write is False
    assert cfg.toolsets == ["all"]
    assert cfg.is_mutate_enabled is False
    assert cfg.is_read_enabled is True


def test_server_config_mutate_enabled_combinations() -> None:
    """is_mutate_enabled requires both allow_write=True and mutate/all toolset."""
    cfg_write_all = ServerConfig(allow_write=True, toolsets=["all"])
    assert cfg_write_all.is_mutate_enabled is True
    assert cfg_write_all.is_read_enabled is True

    cfg_write_read_only_toolset = ServerConfig(allow_write=True, toolsets=["read"])
    assert cfg_write_read_only_toolset.is_mutate_enabled is False
    assert cfg_write_read_only_toolset.is_read_enabled is True

    cfg_write_mutate_only = ServerConfig(allow_write=True, toolsets=["mutate"])
    assert cfg_write_mutate_only.is_mutate_enabled is True
    assert cfg_write_mutate_only.is_read_enabled is False

    cfg_readonly_flag = ServerConfig(allow_write=True, toolsets=["readonly"])
    assert cfg_readonly_flag.is_mutate_enabled is False
    assert cfg_readonly_flag.is_read_enabled is True


def test_config_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config.from_env() should default to allow_write=False when env vars are unset."""
    monkeypatch.delenv("MCP_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("MCP_TOOLSETS", raising=False)
    monkeypatch.delenv("MCP_READ_ONLY", raising=False)
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)

    cfg = Config.from_env()
    assert cfg.allow_write is False
    assert cfg.is_mutate_enabled is False
    assert cfg.transport == "stdio"


def test_config_from_env_write_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config.from_env() should enable write mode when MCP_ALLOW_WRITE=true."""
    monkeypatch.setenv("MCP_ALLOW_WRITE", "true")
    monkeypatch.setenv("MCP_TOOLSETS", "read,mutate")
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MCP_PORT", "9090")
    monkeypatch.setenv("KUBECONFIG", "/custom/kubeconfig")

    cfg = Config.from_env()
    assert cfg.allow_write is True
    assert cfg.toolsets == ["read", "mutate"]
    assert cfg.is_mutate_enabled is True
    assert cfg.transport == "http"
    assert cfg.port == 9090
    assert cfg.kubernetes.kubeconfig == "/custom/kubeconfig"


def test_config_from_env_read_only_overrides_allow_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP_READ_ONLY=true should force allow_write=False even if MCP_ALLOW_WRITE=true."""
    monkeypatch.setenv("MCP_ALLOW_WRITE", "true")
    monkeypatch.setenv("MCP_READ_ONLY", "true")

    cfg = Config.from_env()
    assert cfg.allow_write is False
    assert cfg.toolsets == ["read"]
    assert cfg.is_mutate_enabled is False


def test_apply_cli_overrides() -> None:
    """CLI flags should override environment-loaded ServerConfig attributes."""
    cfg = ServerConfig(allow_write=False, transport="stdio")
    apply_cli_overrides(
        cfg,
        [
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            "8888",
            "--allow-write",
            "--toolsets",
            "read,mutate",
        ],
    )
    assert cfg.transport == "http"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8888
    assert cfg.allow_write is True
    assert cfg.toolsets == ["read", "mutate"]
    assert cfg.is_mutate_enabled is True

    # --read-only should force allow_write=False and toolsets=["read"]
    apply_cli_overrides(cfg, ["--read-only"])
    assert cfg.allow_write is False
    assert cfg.toolsets == ["read"]
    assert cfg.is_mutate_enabled is False
