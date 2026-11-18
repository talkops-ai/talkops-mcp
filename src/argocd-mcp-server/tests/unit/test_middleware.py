"""Unit tests for FastMCP middleware configuration (audit findings N1 and N8)."""

from fastmcp import FastMCP
from fastmcp.server.middleware.caching import ResponseCachingMiddleware
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.server.middleware import setup_middleware


def test_middleware_disables_call_tool_and_read_resource_caching(
    write_config: ServerConfig,
) -> None:
    """ResponseCachingMiddleware must NOT cache call_tool or read_resource (Fixes N1)."""
    mcp = FastMCP("test-argocd")
    setup_middleware(mcp, write_config)

    caching_middlewares = [
        m for m in mcp.middleware if isinstance(m, ResponseCachingMiddleware)
    ]
    assert len(caching_middlewares) == 1
    cm = caching_middlewares[0]
    assert cm._call_tool_settings.get("enabled") is False
    assert cm._read_resource_settings.get("enabled") is False
    assert cm._list_tools_settings.get("enabled") is True


def test_structured_logging_disables_payload_logging(
    write_config: ServerConfig,
) -> None:
    """StructuredLoggingMiddleware must set include_payloads=False to avoid secret leakage (Fixes N8)."""
    mcp = FastMCP("test-argocd")
    setup_middleware(mcp, write_config)

    logging_middlewares = [
        m for m in mcp.middleware if isinstance(m, StructuredLoggingMiddleware)
    ]
    assert len(logging_middlewares) == 1
    assert logging_middlewares[0].include_payloads is False
