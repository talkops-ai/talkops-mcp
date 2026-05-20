"""Middleware setup for FastMCP server."""

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.server.middleware.caching import (
    ResponseCachingMiddleware,
    ListToolsSettings,
    ListResourcesSettings,
    ListPromptsSettings,
    CallToolSettings,
    ReadResourceSettings,
    GetPromptSettings,
)
from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext
from fastmcp.tools.base import ToolResult
from fastmcp.resources.base import ResourceResult
from fastmcp.prompts.base import PromptResult
from kargo_mcp_server.config import ServerConfig


class RequestResponseTransformationMiddleware(Middleware):
    """Middleware for transforming requests and responses.

    Allows modification of data before it reaches tools or after it leaves them.
    Use cases include sanitizing input, adding metadata, or normalizing formats.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        """Transform tool call requests and responses."""
        result = await call_next(context)
        return result

    async def on_read_resource(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ResourceResult],
    ) -> ResourceResult:
        """Transform resource read requests and responses."""
        result = await call_next(context)
        return result

    async def on_get_prompt(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, PromptResult],
    ) -> PromptResult:
        """Transform prompt get requests and responses."""
        result = await call_next(context)
        return result


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.

    Middleware order:
    1. Error Handling - catches and transforms errors
    2. Request/Response Transformation - modifies data
    3. Caching - checks cache before execution
    4. Logging - tracks all operations
    5. Timing - measures performance

    Args:
        mcp: FastMCP server instance
        config: Server configuration
    """
    # 1. Error Handling
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=False,
        transform_errors=True,
    ))

    # 2. Request/Response Transformation
    mcp.add_middleware(RequestResponseTransformationMiddleware())

    # 3. Caching — short TTL for Kargo state since promotions change frequently
    mcp.add_middleware(ResponseCachingMiddleware(
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        call_tool_settings=CallToolSettings(ttl=30, enabled=True),
        read_resource_settings=ReadResourceSettings(ttl=30, enabled=True),
        get_prompt_settings=GetPromptSettings(ttl=3600, enabled=True),
    ))

    # 4. Logging
    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=True,
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))

    # 5. Timing
    mcp.add_middleware(TimingMiddleware())
