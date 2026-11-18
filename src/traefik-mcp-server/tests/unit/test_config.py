"""Unit tests for ServerConfig, CLI flags, environment variables, and toolset gating."""

import pytest
from traefik_mcp_server.config import Config, ServerConfig, VALID_TOOLSETS


def test_default_config_is_stdio_and_read_only():
    cfg = ServerConfig()
    assert cfg.transport == "stdio"
    assert cfg.allow_write is False
    assert cfg.toolsets == ["all"]
    assert VALID_TOOLSETS == frozenset({"all", "readonly", "traffic", "policies", "diagnostics"})


def test_non_stdio_transport_rejected():
    with pytest.raises(ValueError, match="stdio"):
        ServerConfig(transport="streamable-http")


def test_unknown_toolset_rejected():
    with pytest.raises(ValueError, match="Invalid toolset"):
        ServerConfig(toolsets=["unknown_set"])


def test_cli_flags_override_env(monkeypatch):
    monkeypatch.setenv("MCP_ALLOW_WRITE", "false")
    monkeypatch.setenv("MCP_TOOLSETS", "diagnostics")
    cfg = Config.from_cli_and_env([
        "--allow-write",
        "--toolsets",
        "traffic,policies",
        "--prometheus-url",
        "http://prom:9090",
        "--traefik-namespace",
        "edge-system",
        "--allowed-namespaces",
        "default,staging",
    ])
    assert cfg.allow_write is True
    assert cfg.toolsets == ["traffic", "policies"]
    assert cfg.prometheus_url == "http://prom:9090"
    assert cfg.traefik_namespace == "edge-system"
    assert cfg.allowed_namespaces == ["default", "staging"]


def test_should_register_matrix():
    ro_all = ServerConfig(allow_write=False, toolsets=["all"])
    assert ro_all.should_register("diagnostics", is_write=False) is True
    assert ro_all.should_register("traffic", is_write=True) is False
    assert ro_all.should_register("policies", is_write=True) is False

    rw_traffic = ServerConfig(allow_write=True, toolsets=["traffic"])
    assert rw_traffic.should_register("traffic", is_write=True) is True
    assert rw_traffic.should_register("policies", is_write=True) is False
    assert rw_traffic.should_register("diagnostics", is_write=False) is False

    rw_readonly = ServerConfig(allow_write=True, toolsets=["readonly"])
    assert rw_readonly.should_register("diagnostics", is_write=False) is True
    assert rw_readonly.should_register("traffic", is_write=True) is False
