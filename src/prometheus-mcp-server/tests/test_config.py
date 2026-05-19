"""Tests for configuration module."""

import json
import os
from unittest.mock import patch

import pytest

from prometheus_mcp_server.config import BackendConfig, Config, KubernetesConfig, ServerConfig


class TestConfig:
    """Test configuration loading."""

    @patch('dotenv.load_dotenv')
    def test_default_config(self, mock_load_dotenv):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            assert config.name == 'prometheus-mcp-server'
            assert config.transport == 'stdio'
            assert len(config.backends) == 1
            assert config.backends[0].id == 'default'
            assert config.backends[0].base_url == 'http://localhost:9090'

    def test_single_backend_from_env(self):
        env = {
            'PROMETHEUS_BASE_URL': 'http://prom.example.com:9090',
            'PROMETHEUS_BACKEND_ID': 'prod',
            'PROMETHEUS_TYPE': 'thanos',
            'PROMETHEUS_VERIFY_SSL': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert len(config.backends) == 1
            assert config.backends[0].id == 'prod'
            assert config.backends[0].base_url == 'http://prom.example.com:9090'
            assert config.backends[0].type == 'thanos'
            assert config.backends[0].verify_ssl is False

    def test_multi_backend_from_env(self):
        backends = [
            {"id": "dev", "base_url": "http://dev:9090", "type": "prometheus"},
            {"id": "prod", "base_url": "http://prod:9090", "type": "thanos", "labels": {"env": "prod"}},
        ]
        env = {'PROMETHEUS_BACKENDS': json.dumps(backends)}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert len(config.backends) == 2
            assert config.backends[0].id == 'dev'
            assert config.backends[1].id == 'prod'
            assert config.backends[1].type == 'thanos'
            assert config.backends[1].labels == {"env": "prod"}

    def test_invalid_backends_json_falls_back(self):
        env = {'PROMETHEUS_BACKENDS': 'invalid json'}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert len(config.backends) == 1
            assert config.backends[0].id == 'default'

    def test_kubernetes_config(self):
        env = {
            'K8S_CONTEXT': 'my-context',
            'K8S_IN_CLUSTER': 'true',
            'K8S_ENABLED': 'true',
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.kubernetes.context_name == 'my-context'
            assert config.kubernetes.in_cluster is True
            assert config.kubernetes.enabled is True

    def test_server_config_fields(self):
        env = {
            'MCP_TRANSPORT': 'http',
            'MCP_PORT': '8080',
            'MCP_LOG_LEVEL': 'DEBUG',
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.transport == 'http'
            assert config.port == 8080
            assert config.logging.level == 'DEBUG'


class TestBackendConfig:
    """Test BackendConfig dataclass."""

    def test_default_values(self):
        bc = BackendConfig()
        assert bc.id == 'default'
        assert bc.base_url == 'http://localhost:9090'
        assert bc.type == 'prometheus'
        assert bc.verify_ssl is True
        assert bc.timeout == 30
