"""Tests for server bootstrap."""
import os
from unittest.mock import patch
import pytest
from alertmanager_mcp_server.server.bootstrap import ServerBootstrap


class TestServerBootstrap:
    def test_initialize_creates_server(self):
        env = {'ALERTMANAGER_BASE_URL': 'http://localhost:9093', 'MCP_TRANSPORT': 'stdio'}
        with patch.dict(os.environ, env, clear=True):
            mcp, config, service = ServerBootstrap.initialize()
            assert mcp is not None
            assert config.name == 'alertmanager-mcp-server'
            assert len(config.backends) == 1
