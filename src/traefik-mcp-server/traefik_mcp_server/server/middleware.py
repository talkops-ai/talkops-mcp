"""Middleware setup for FastMCP server."""
import json
import yaml

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
from traefik_mcp_server.config import ServerConfig


class JsonCoercionMiddleware(Middleware):
    """Middleware to coerce stringified JSON/YAML arguments into native objects.
    
    Agents often fail to send proper JSON objects for tool parameters defined as
    `dict` or `list`, instead sending stringified JSON or YAML. Pydantic validation
    fails immediately before the tool is even called.
    
    This middleware intercepts the request BEFORE Pydantic validation and attempts
    to parse any strings that look like JSON objects or arrays into actual Python
    dicts/lists.
    """
    
    def _try_parse(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
            
        stripped = value.strip()
        # Only attempt to parse things that look like objects or arrays
        if not (
            (stripped.startswith('{') and stripped.endswith('}')) or 
            (stripped.startswith('[') and stripped.endswith(']'))
        ):
            return value
            
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            try:
                parsed = yaml.safe_load(stripped)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except yaml.YAMLError:
                pass
                
        return value

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        """Coerce tool arguments before execution."""
        if hasattr(context.message, 'arguments') and isinstance(context.message.arguments, dict):
            for key, value in context.message.arguments.items():
                context.message.arguments[key] = self._try_parse(value)
                
        return await call_next(context)


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
        include_traceback=config.debug,  # Show tracebacks in debug mode
        transform_errors=True,
    ))
    
    # 2. Request/Response Transformation - Modify data before it reaches tools or after it leaves
    mcp.add_middleware(JsonCoercionMiddleware())
    
    # 3. Caching - Store frequently requested data to improve performance
    # Caches tools/list, resources/list, prompts/list, tools/call, resources/read, prompts/get
    # Using TypedDict settings classes as per FastMCP documentation
    mcp.add_middleware(ResponseCachingMiddleware(
        # Cache list operations for 5 minutes (300 seconds)
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        # Cache tool calls for 30 minutes (1800 seconds) - adjusted for ArgoFlow
        call_tool_settings=CallToolSettings(ttl=30, enabled=True),
        # Cache resource reads for 30 minutes
        read_resource_settings=ReadResourceSettings(ttl=30, enabled=True),
        # Cache prompt gets for 1 hour
        get_prompt_settings=GetPromptSettings(ttl=3600, enabled=True),
    ))
    
    # 4. Logging and Monitoring - Track usage patterns and performance metrics
    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=config.debug,  # Only include payloads in debug mode
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))
    
    # 5. Timing - Measure request execution time (part of monitoring)
    mcp.add_middleware(TimingMiddleware())
