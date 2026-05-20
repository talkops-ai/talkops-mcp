"""Middleware setup for Terraform MCP Server.

Middleware executes in the order added. Tuned for Terraform workloads:
- Search / ingestion tool calls have shorter cache TTLs (60s)
- Resource reads (stats, config) cached moderately (120s)
- List operations cached aggressively (300s)
"""

from collections.abc import Sequence
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
from fastmcp.tools.tool import ToolResult
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import GetPromptResult
from terraform_mcp_server.server_config import ServerConfig


class RequestResponseTransformationMiddleware(Middleware):
    """Middleware for transforming requests and responses.
    
    Extensible pass-through middleware for future use cases such as:
    - Input sanitization
    - Response metadata injection
    - Correlation ID tracking
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
        call_next: CallNext[Any, Sequence[ReadResourceContents]],
    ) -> Sequence[ReadResourceContents]:
        """Transform resource read requests and responses."""
        result = await call_next(context)
        return result
    
    async def on_get_prompt(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, GetPromptResult],
    ) -> GetPromptResult:
        """Transform prompt get requests and responses."""
        result = await call_next(context)
        return result


def setup_middleware(mcp: FastMCP, server_config: ServerConfig) -> None:
    """Configure the middleware stack for the FastMCP server.
    
    Middleware order:
    1. Error Handling — consistent error responses
    2. Request/Response Transformation — extensible pass-through
    3. Response Caching — tuned TTLs for Terraform workloads
    4. Structured Logging — operational visibility
    5. Timing — performance measurement
    
    Args:
        mcp: FastMCP server instance
        server_config: Server configuration for debug flags
    """
    # 1. Error Handling
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=server_config.debug,
        transform_errors=True,
    ))
    
    # 2. Request/Response Transformation (extensible)
    mcp.add_middleware(RequestResponseTransformationMiddleware())
    
    # 3. Response Caching — tuned for Terraform workloads
    # List operations: 5 min (stable metadata)
    # Tool calls: 60s (search/ingestion results change frequently)
    # Resource reads: 120s (stats/config moderately dynamic)
    mcp.add_middleware(ResponseCachingMiddleware(
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        call_tool_settings=CallToolSettings(ttl=60, enabled=True),
        read_resource_settings=ReadResourceSettings(ttl=120, enabled=True),
        get_prompt_settings=GetPromptSettings(ttl=3600, enabled=True),
    ))
    
    # 4. Structured Logging
    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=server_config.debug,
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))
    
    # 5. Timing
    mcp.add_middleware(TimingMiddleware())
