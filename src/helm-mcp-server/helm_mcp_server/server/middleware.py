"""Middleware setup for FastMCP server."""

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
from helm_mcp_server.config import ServerConfig


class RequestResponseTransformationMiddleware(Middleware):
    """Middleware for transforming requests and responses.
    
    This middleware allows you to modify data before it reaches tools
    or after it leaves them. Example use cases:
    - Sanitizing input data
    - Adding metadata to responses
    - Normalizing data formats
    - Adding request IDs or correlation IDs
    
    Following FastMCP middleware patterns from:
    https://gofastmcp.com/servers/middleware
    """
    
    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        """Transform tool call requests and responses."""
        # Transform request if needed (before execution)
        # Example: You could modify context.message.params here
        
        # Execute the tool
        result = await call_next(context)
        
        # Transform response if needed (after execution)
        # Example: You could modify result here
        
        return result
    
    async def on_read_resource(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[ReadResourceContents]],
    ) -> Sequence[ReadResourceContents]:
        """Transform resource read requests and responses."""
        result = await call_next(context)
        # Transform resource response if needed
        return result
    
    async def on_get_prompt(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, GetPromptResult],
    ) -> GetPromptResult:
        """Transform prompt get requests and responses."""
        result = await call_next(context)
        # Transform prompt response if needed
        return result


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.
    
    Middleware order matters - they execute in the order added:
    1. Error Handling - catches and transforms errors first
    2. Request/Response Transformation - modifies data before/after execution
    3. Caching - checks cache before execution
    4. Logging - tracks all operations
    5. Timing - measures performance
    
    Args:
        mcp: FastMCP server instance
        config: Server configuration
    """
    # 1. Error Handling - Provide consistent error responses
    # Set include_traceback=False to show clean error messages without stack traces
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=False,
        transform_errors=True,
    ))
    
    # 2. Request/Response Transformation - Modify data before it reaches tools or after it leaves
    mcp.add_middleware(RequestResponseTransformationMiddleware())
    
    # 3. Caching - Store frequently requested data to improve performance
    # Caches tools/list, resources/list, prompts/list, tools/call, resources/read, prompts/get
    # Using TypedDict settings classes as per FastMCP documentation
    mcp.add_middleware(ResponseCachingMiddleware(
        # Cache list operations for 5 minutes (300 seconds)
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        # Cache tool calls for 1 hour (3600 seconds) - adjust based on your needs
        call_tool_settings=CallToolSettings(ttl=3600, enabled=True),
        # Cache resource reads for 1 hour
        read_resource_settings=ReadResourceSettings(ttl=3600, enabled=True),
        # Cache prompt gets for 1 hour
        get_prompt_settings=GetPromptSettings(ttl=3600, enabled=True),
    ))
    
    # 4. Logging and Monitoring - Track usage patterns and performance metrics
    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=True,
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))
    
    # 5. Timing - Measure request execution time (part of monitoring)
    mcp.add_middleware(TimingMiddleware())
