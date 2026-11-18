"""Unit tests for configuration, CLI argument overrides, and toolset gating."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from prometheus_mcp_server.config import BackendConfig, Config, ServerConfig


class TestConfigAndCli:
    @patch("dotenv.load_dotenv")
    def test_default_config_from_env(self, _mock_dotenv) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = Config.from_env()
            assert cfg.name == "prometheus-mcp-server"
            assert cfg.version == "0.2.0"
            assert cfg.transport == "stdio"
            assert cfg.allow_write is True
            assert cfg.toolsets == ["all"]
            assert len(cfg.backends) == 1
            assert cfg.backends[0].id == "default"

    @patch("dotenv.load_dotenv")
    def test_read_only_and_toolsets_from_env(self, _mock_dotenv) -> None:
        env = {
            "MCP_ALLOW_WRITE": "false",
            "PROMETHEUS_TOOLSETS": "diagnostics,query",
            "PROMETHEUS_TENANT_ID": "tenant-a",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = Config.from_env()
            assert cfg.allow_write is False
            assert cfg.toolsets == ["diagnostics", "query"]
            assert cfg.backends[0].tenant_id == "tenant-a"
            assert cfg.should_register("diagnostics", is_write=False) is True
            assert cfg.should_register("rules", is_write=False) is False
            assert cfg.should_register("exporter", is_write=True) is False

    @patch("dotenv.load_dotenv")
    def test_cli_overrides_env(self, _mock_dotenv) -> None:
        with patch.dict(os.environ, {"MCP_ALLOW_WRITE": "true"}, clear=True):
            cfg = Config.from_cli_and_env(
                [
                    "--read-only",
                    "--toolsets",
                    "query,rules",
                    "--prometheus-url",
                    "http://mimir:9009/prometheus",
                    "--tenant-id",
                    "org-42",
                ]
            )
            assert cfg.allow_write is False
            assert cfg.toolsets == ["query", "rules"]
            assert cfg.backends[0].base_url == "http://mimir:9009/prometheus"
            assert cfg.backends[0].tenant_id == "org-42"

    def test_invalid_toolset_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid toolset"):
            ServerConfig(toolsets=["unknown_toolset"])

    def test_multi_backend_json_parsing(self) -> None:
        backends = [
            {
                "id": "prom-eu",
                "base_url": "http://prom-eu:9090",
                "type": "thanos",
                "tenant_id": "eu-1",
            }
        ]
        with patch.dict(
            os.environ, {"PROMETHEUS_BACKENDS": json.dumps(backends)}, clear=True
        ):
            cfg = Config.from_env()
            assert len(cfg.backends) == 1
            assert cfg.backends[0].id == "prom-eu"
            assert cfg.backends[0].tenant_id == "eu-1"
            assert cfg.backends[0].type == "thanos"

    @patch("dotenv.load_dotenv")
    def test_empty_env_fallback_and_prometheus_url_alias(self, _mock_dotenv) -> None:
        env = {
            "PROMETHEUS_BASE_URL": "",
            "PROMETHEUS_URL": "http://localhost:19090",
            "K8S_CONTEXT": "",
            "KUBE_CONTEXT": "docker-desktop",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = Config.from_env()
            assert cfg.backends[0].base_url == "http://localhost:19090"
            assert cfg.kubernetes.context_name == "docker-desktop"
