"""Tests for middleware configuration."""

import pytest
from fastmcp import FastMCP

from terraform_mcp_server.server_config import ServerConfig
from terraform_mcp_server.server.middleware import setup_middleware


class TestMiddlewareConfig:
    """Test middleware setup on a fresh FastMCP instance."""
    
    def test_setup_middleware_does_not_raise(self):
        """setup_middleware should not raise on a fresh FastMCP."""
        mcp = FastMCP(name='test-server', version='0.0.1')
        config = ServerConfig(debug=False)
        
        # Should not raise
        setup_middleware(mcp, config)
    
    def test_setup_middleware_debug_mode(self):
        """setup_middleware with debug=True should not raise."""
        mcp = FastMCP(name='test-server', version='0.0.1')
        config = ServerConfig(debug=True)
        
        setup_middleware(mcp, config)
    
    def test_create_mcp_server_returns_fastmcp(self):
        """create_mcp_server returns a FastMCP instance with middleware."""
        from terraform_mcp_server.server.core import create_mcp_server
        
        config = ServerConfig(
            name='test',
            version='0.0.1',
            debug=False,
        )
        mcp = create_mcp_server(config)
        
        assert isinstance(mcp, FastMCP)
