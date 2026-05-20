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
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext
from fastmcp.tools.base import ToolResult
from fastmcp.resources.base import ResourceResult
from fastmcp.prompts.base import PromptResult
from prometheus_mcp_server.config import ServerConfig


class RequestResponseTransformationMiddleware(Middleware):
    """Middleware for transforming requests and responses."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        return result

    async def on_read_resource(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ResourceResult],
    ) -> ResourceResult:
        result = await call_next(context)
        return result

    async def on_get_prompt(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, PromptResult],
    ) -> PromptResult:
        result = await call_next(context)
        return result


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.

    Middleware order:
    1. Error Handling - catches and transforms errors
    2. Response Limiting - prevents massive payloads from crashing context
    3. Rate Limiting - protects against abusive or runaway requests
    4. Request/Response Transformation - modifies data
    5. Caching - checks cache before execution
    6. Logging - tracks all operations
    7. Timing - measures performance
    """
    # 1. Error Handling
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=False,
        transform_errors=True,
    ))

    # 2. Response Limiting
    mcp.add_middleware(ResponseLimitingMiddleware(
        max_size=100_000,
    ))

    # 3. Rate Limiting
    mcp.add_middleware(RateLimitingMiddleware(
        max_requests_per_second=10.0,
        burst_capacity=20,
        global_limit=True,
    ))

    # 4. Request/Response Transformation
    mcp.add_middleware(RequestResponseTransformationMiddleware())

    # 5. Caching — shorter TTL for Prometheus (metrics change frequently)
    mcp.add_middleware(ResponseCachingMiddleware(
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        call_tool_settings=CallToolSettings(ttl=15, enabled=True),
        read_resource_settings=ReadResourceSettings(ttl=30, enabled=True),
        get_prompt_settings=GetPromptSettings(ttl=3600, enabled=True),
    ))

    # 6. Logging
    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=True,
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))

    # 7. Timing
    mcp.add_middleware(TimingMiddleware())
