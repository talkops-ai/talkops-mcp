"""Tests for server bootstrap."""

import os
from unittest.mock import patch

import pytest

from prometheus_mcp_server.server.bootstrap import ServerBootstrap


class TestServerBootstrap:
    def test_initialize_creates_server(self):
        env = {
            'PROMETHEUS_BASE_URL': 'http://localhost:9090',
            'PROMETHEUS_VERIFY_SSL': 'false',
            'MCP_TRANSPORT': 'stdio',
            'K8S_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            mcp, config = ServerBootstrap.initialize()
            assert mcp is not None
            assert config.name == 'prometheus-mcp-server'
            assert len(config.backends) == 1
