"""Unit tests for config module.

Per test guide §5: Direct Python calls, no MCP involved.
"""

import os
from unittest.mock import patch

import pytest

from loki_mcp_server.config import Config, ServerConfig


class TestConfigDefaults:
    """Test that Config.from_env() produces sensible defaults."""

    def test_default_loki_url(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            assert config.loki.base_url in ("http://loki:3100", "http://localhost:3100")

    def test_default_transport(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            assert config.transport in ("stdio", "streamable-http")

    def test_default_guardrails(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            assert config.guardrails.max_query_bytes == 5_000_000_000
            assert config.guardrails.max_time_window_hours == 336
            assert config.guardrails.max_log_limit == 200
            assert config.guardrails.high_cardinality_threshold == 10_000


class TestConfigOverrides:
    """Test environment variable overrides."""

    def test_loki_url_override(self):
        env = {"LOKI_URL": "http://custom:9090"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.loki.base_url == "http://custom:9090"

    def test_auth_token_override(self):
        env = {"LOKI_AUTH_TOKEN": "my-secret-token"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.auth.auth_token == "my-secret-token"

    def test_basic_auth_override(self):
        env = {
            "LOKI_BASIC_AUTH_USER": "admin",
            "LOKI_BASIC_AUTH_PASSWORD": "password123",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.auth.basic_auth_user == "admin"
            assert config.auth.basic_auth_password == "password123"

    def test_org_id_override(self):
        env = {"LOKI_ORG_ID": "team-alpha"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.auth.org_id == "team-alpha"

    def test_guardrails_override(self):
        env = {
            "LOKI_MAX_QUERY_BYTES": "1000000000",
            "LOKI_MAX_LOG_LIMIT": "2000",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.guardrails.max_query_bytes == 1_000_000_000
            assert config.guardrails.max_log_limit == 2000

    def test_ssl_verify_false(self):
        env = {"LOKI_VERIFY_SSL": "false"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.loki.verify_ssl is False


class TestConfigImmutability:
    """Test that config objects are immutable (frozen)."""

    def test_server_config_frozen(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            with pytest.raises(AttributeError):
                config.name = "changed"  # type: ignore[misc]

    def test_loki_config_frozen(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            with pytest.raises(AttributeError):
                config.loki.base_url = "changed"  # type: ignore[misc]
