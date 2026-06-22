"""Tests for server bootstrap."""

import pytest

from opentelemetry_mcp_server.server.bootstrap import ServerBootstrap
from opentelemetry_mcp_server.config import ServerConfig

class TestServerBootstrap:
    """Test server initialization."""

    def test_initialize_returns_tuple(self) -> None:
        mcp, config = ServerBootstrap.initialize()
        assert mcp is not None
        assert isinstance(config, ServerConfig)
        assert config.name == "opentelemetry-mcp-server"
