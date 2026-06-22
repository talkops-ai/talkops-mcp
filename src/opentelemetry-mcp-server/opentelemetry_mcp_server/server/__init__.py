"""Server module."""

from opentelemetry_mcp_server.server.bootstrap import ServerBootstrap
from opentelemetry_mcp_server.server.core import create_mcp_server

__all__ = [
    "ServerBootstrap",
    "create_mcp_server",
]
