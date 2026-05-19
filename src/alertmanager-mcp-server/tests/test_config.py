"""Tests for configuration module."""
import json
import os
from unittest.mock import patch
import pytest
from alertmanager_mcp_server.config import BackendConfig, Config


class TestConfig:
    def test_default_config(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            assert config.name == 'alertmanager-mcp-server'
            assert len(config.backends) == 1
            assert config.backends[0].id == 'default'
            assert config.backends[0].base_url == 'http://localhost:9093'

    def test_single_backend_from_env(self):
        env = {'ALERTMANAGER_BASE_URL': 'http://am.example.com:9093', 'ALERTMANAGER_BACKEND_ID': 'prod-am'}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
            assert config.backends[0].id == 'prod-am'
            assert config.backends[0].base_url == 'http://am.example.com:9093'

    def test_multi_backend_from_env(self):
        backends = [
            {"id": "dev-am", "base_url": "http://dev:9093"},
            {"id": "prod-am", "base_url": "http://prod:9093", "labels": {"env": "prod"}},
        ]
        with patch.dict(os.environ, {'ALERTMANAGER_BACKENDS': json.dumps(backends)}, clear=True):
            config = Config.from_env()
            assert len(config.backends) == 2
            assert config.backends[1].labels == {"env": "prod"}

    def test_invalid_json_falls_back(self):
        with patch.dict(os.environ, {'ALERTMANAGER_BACKENDS': 'bad json'}, clear=True):
            config = Config.from_env()
            assert len(config.backends) == 1

    def test_silence_safety_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config.from_env()
            assert config.max_silence_duration_minutes == 1440
            assert config.silence_warning_threshold == 50


class TestBackendConfig:
    def test_default_values(self):
        bc = BackendConfig()
        assert bc.id == 'default'
        assert bc.base_url == 'http://localhost:9093'
        assert bc.is_default is True
