"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest

from kargo_mcp_server.config import AuthMode, Config, KargoConfig, LoggingConfig, ServerConfig


class TestServerConfig:
    """Test ServerConfig defaults."""

    def test_default_values(self):
        """ServerConfig should have sensible defaults."""
        config = ServerConfig()
        assert config.name == "kargo-mcp-server"
        assert config.version == "0.1.0"
        assert config.transport == "http"
        assert config.host == "0.0.0.0"
        assert config.port == 8766
        assert config.path == "/mcp"
        assert config.allow_write is True

    def test_kargo_config_defaults(self):
        """KargoConfig should default to localhost admin mode."""
        config = KargoConfig()
        assert config.base_url == "http://localhost:8080"
        assert config.auth_mode == AuthMode.ADMIN
        assert config.verify_ssl is True
        assert config.timeout == 30

    def test_auth_modes(self):
        """AuthMode enum values."""
        assert AuthMode.ADMIN.value == "admin"
        assert AuthMode.STATIC.value == "static"
        assert AuthMode.PASSTHROUGH.value == "passthrough"


class TestConfigFromEnv:
    """Test Config.from_env() environment loading."""

    def test_defaults_without_env(self):
        """Config.from_env should return defaults when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
        assert config.name == "kargo-mcp-server"
        assert config.kargo.base_url == "http://localhost:8080"
        assert config.kargo.auth_mode == AuthMode.ADMIN

    def test_custom_env_vars(self):
        """Config.from_env should read custom env vars."""
        env = {
            "MCP_SERVER_NAME": "my-kargo",
            "MCP_PORT": "9000",
            "MCP_ALLOW_WRITE": "false",
            "KARGO_BASE_URL": "https://kargo.example.com",
            "KARGO_AUTH_MODE": "static",
            "KARGO_STATIC_BEARER_TOKEN": "my-token",
            "KARGO_TIMEOUT": "60",
            "KARGO_VERIFY_SSL": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        assert config.name == "my-kargo"
        assert config.port == 9000
        assert config.allow_write is False
        assert config.kargo.base_url == "https://kargo.example.com"
        assert config.kargo.auth_mode == AuthMode.STATIC
        assert config.kargo.static_bearer_token == "my-token"
        assert config.kargo.timeout == 60
        assert config.kargo.verify_ssl is False

    def test_invalid_auth_mode_defaults_to_admin(self):
        """Invalid auth mode should default to ADMIN."""
        with patch.dict(os.environ, {"KARGO_AUTH_MODE": "invalid"}, clear=True):
            config = Config.from_env()
        assert config.kargo.auth_mode == AuthMode.ADMIN

    def test_passthrough_auth_mode(self):
        """PASSTHROUGH auth mode should be recognized."""
        with patch.dict(os.environ, {"KARGO_AUTH_MODE": "passthrough"}, clear=True):
            config = Config.from_env()
        assert config.kargo.auth_mode == AuthMode.PASSTHROUGH
