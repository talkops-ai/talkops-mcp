"""Unit tests for ServerConfig and environment variable loading."""

import pytest
from argocd_mcp_server.config import Config
from argocd_mcp_server.main import parse_args


def test_default_config_safe_posture(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP_ALLOW_WRITE must default to False for safe read-only posture."""
    monkeypatch.delenv("MCP_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("MCP_TOOLSETS", raising=False)
    monkeypatch.delenv("ARGOCD_SERVER_URL", raising=False)

    cfg = Config.from_env()
    assert cfg.allow_write is False
    assert cfg.toolsets == ["all"]
    assert cfg.argocd.server_url == "https://argocd-server.argocd.svc:443"
    assert cfg.version == "0.4.0"


def test_config_from_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables populate ServerConfig, ArgoCDConfig, and GitConfig."""
    monkeypatch.setenv("MCP_ALLOW_WRITE", "true")
    monkeypatch.setenv("MCP_TOOLSETS", "applications,deployments")
    monkeypatch.setenv("ARGOCD_SERVER_URL", "https://argocd.internal:8443")
    monkeypatch.setenv("ARGOCD_AUTH_TOKEN", "jwt-secret")
    monkeypatch.setenv("ARGOCD_INSECURE", "true")
    monkeypatch.setenv("ARGOCD_MAX_RETRIES", "3")
    monkeypatch.setenv("GIT_USERNAME", "ci-user")
    monkeypatch.setenv("GIT_PASSWORD", "ci-pass")

    cfg = Config.from_env()
    assert cfg.allow_write is True
    assert cfg.toolsets == ["applications", "deployments"]
    assert cfg.argocd.server_url == "https://argocd.internal:8443"
    assert cfg.argocd.auth_token == "jwt-secret"
    assert cfg.argocd.insecure is True
    assert cfg.argocd.max_retries == 3
    assert cfg.git.username == "ci-user"
    assert cfg.git.password == "ci-pass"


def test_readonly_toolset_forces_allow_write_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting MCP_TOOLSETS=readonly forces allow_write=False even if MCP_ALLOW_WRITE=true."""
    monkeypatch.setenv("MCP_ALLOW_WRITE", "true")
    monkeypatch.setenv("MCP_TOOLSETS", "readonly")

    cfg = Config.from_env()
    assert cfg.allow_write is False


def test_cli_parse_args() -> None:
    """CLI parser supports --transport, --toolsets, and --read-only."""
    args = parse_args(["--transport", "http", "--toolsets", "applications,projects", "--read-only"])
    assert args.transport == "http"
    assert args.toolsets == "applications,projects"
    assert args.read_only is True
