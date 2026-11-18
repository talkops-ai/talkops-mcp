"""T-U8: Tests for configuration loading, CLI flags, toolset gating, and B3 dotenv fix."""

import ast
import inspect
import os
import textwrap
from unittest.mock import patch

import pytest

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
        assert config.allow_write is False
        assert config.write_enabled is False
        assert config.collector_version_default == "0.152.1"

    def test_kubernetes_defaults(self) -> None:
        config = ServerConfig()
        assert config.kubernetes.enabled is True
        assert config.kubernetes.in_cluster is False
        assert config.kubernetes.context_name is None

    def test_otel_operator_defaults(self) -> None:
        config = ServerConfig()
        assert config.otel_operator.crd_group == "opentelemetry.io"
        assert config.otel_operator.crd_api_version == "v1beta1"
        assert config.otel_operator.collector_plural == "opentelemetrycollectors"
        assert config.otel_operator.target_allocator_plural == "targetallocators"
        assert config.otel_operator.opamp_bridge_plural == "opampbridges"

    def test_frozen_config(self) -> None:
        config = ServerConfig()
        with pytest.raises(AttributeError):
            config.name = "changed"  # type: ignore[misc]


class TestConfigFromEnvAndCli:
    """Test Config.from_env() and Config.from_cli_and_env()."""

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
            "MCP_ALLOW_WRITE": "true",
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
        assert config.write_enabled is True

    @patch.dict(os.environ, {}, clear=False)
    def test_defaults_from_env(self) -> None:
        config = Config.from_env()
        assert config.name == "opentelemetry-mcp-server"
        assert config.transport == "stdio"

    def test_from_env_does_not_call_load_dotenv(self) -> None:
        """Fix B3: Config.from_env() must not have hidden load_dotenv() side effects."""
        src = textwrap.dedent(inspect.getsource(Config.from_env))
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "load_dotenv"

    def test_cli_flags_override_env(self) -> None:
        cfg = Config.from_cli_and_env(
            [
                "--allow-write",
                "--toolsets",
                "discovery,collector",
                "--kubeconfig",
                "/tmp/kube.cfg",
                "--context",
                "staging-ctx",
            ]
        )
        assert cfg.write_enabled is True
        assert cfg.toolsets == ["discovery", "collector"]
        assert cfg.kubernetes.kubeconfig == "/tmp/kube.cfg"
        assert cfg.kubernetes.context_name == "staging-ctx"

        # --read-only wins over --allow-write
        cfg_ro = Config.from_cli_and_env(["--allow-write", "--read-only"])
        assert cfg_ro.write_enabled is False

    def test_invalid_toolset_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown toolset"):
            Config.from_cli_and_env(["--toolsets", "discovery,nonexistent"])
