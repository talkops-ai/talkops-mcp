"""Tests for configuration loading."""

import os
from unittest.mock import patch

from opentelemetry_mcp_server.config import (
    Config,
    ServerConfig,
)


class TestServerConfig:
    """Test ServerConfig defaults."""

    def test_defaults(self) -> None:
        config = ServerConfig()
        assert config.name == "opentelemetry-mcp-server"
        assert config.transport == "stdio"
        assert config.port == 8768
        assert config.http_timeout == 300

    def test_kubernetes_defaults(self) -> None:
        config = ServerConfig()
        assert config.kubernetes.enabled is True
        assert config.kubernetes.in_cluster is False

    def test_otel_operator_defaults(self) -> None:
        config = ServerConfig()
        assert config.otel_operator.crd_group == "opentelemetry.io"
        assert config.otel_operator.crd_api_version == "v1beta1"
        assert config.otel_operator.collector_plural == "opentelemetrycollectors"

    def test_frozen_config(self) -> None:
        config = ServerConfig()
        try:
            config.name = "changed"  # type: ignore[misc]
            assert False, "Should have raised"
        except AttributeError:
            pass


class TestConfigFromEnv:
    """Test Config.from_env() loading."""

    @patch.dict(
        os.environ,
        {
            "MCP_SERVER_NAME": "test-server",
            "MCP_TRANSPORT": "http",
            "MCP_PORT": "9999",
            "K8S_IN_CLUSTER": "true",
            "K8S_ENABLED": "false",
            "OTEL_CRD_API_VERSION": "v1alpha1",
            "MCP_LOG_LEVEL": "DEBUG",
        },
        clear=False,
    )
    def test_env_overrides(self) -> None:
        config = Config.from_env()
        assert config.name == "test-server"
        assert config.transport == "http"
        assert config.port == 9999
        assert config.kubernetes.in_cluster is True
        assert config.kubernetes.enabled is False
        assert config.otel_operator.crd_api_version == "v1alpha1"
        assert config.logging.level == "DEBUG"

    @patch.dict(os.environ, {}, clear=False)
    def test_defaults_from_env(self) -> None:
        config = Config.from_env()
        assert config.name == "opentelemetry-mcp-server"
        assert config.transport == "stdio"



