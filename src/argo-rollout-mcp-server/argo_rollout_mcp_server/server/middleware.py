"""Middleware setup for FastMCP server."""

import json
import logging
from collections.abc import Sequence
from typing import Any

import yaml

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
from argo_rollout_mcp_server.config import ServerConfig


logger = logging.getLogger(__name__)


class JsonCoercionMiddleware(Middleware):
    """Coerce stringified JSON/YAML arguments into native Python objects.

    LLM agents frequently send ``dict`` and ``list`` tool parameters as
    JSON or YAML **strings** instead of native objects.  Pydantic rejects
    these strings, causing the first 2-3 tool calls to fail before the
    agent discovers the correct format.

    This middleware intercepts ``tools/call`` requests and attempts to
    parse any string argument that looks like a JSON object/array or YAML
    mapping/sequence into the corresponding Python type **before**
    FastMCP's validation layer runs.

    Parse order: ``json.loads`` (fast) → ``yaml.safe_load`` (structured
    config).  Only ``dict`` and ``list`` results are kept; scalar parses
    are discarded to avoid false-positive coercions of plain strings.

    Following FastMCP middleware patterns from:
    https://gofastmcp.com/servers/middleware
    """

    # Characters that hint the string is structured data.
    _STRUCTURAL_CHARS = frozenset("{[")

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _try_parse(value: str) -> Any:
        """Try JSON then YAML; return parsed obj or the original string."""
        # Fast path: JSON
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Slow path: YAML (only when structural chars are present)
        try:
            parsed = yaml.safe_load(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except yaml.YAMLError:
            pass

        return value

    # ── middleware hooks ───────────────────────────────────────────────

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        """Coerce stringified JSON/YAML arguments before tool execution."""
        arguments = getattr(context.message, "arguments", None)
        if arguments and isinstance(arguments, dict):
            for key, value in list(arguments.items()):
                if isinstance(value, str) and value and value[0] in self._STRUCTURAL_CHARS:
                    coerced = self._try_parse(value)
                    if coerced is not value:
                        logger.debug(
                            "JsonCoercionMiddleware: coerced arg '%s' from str → %s",
                            key,
                            type(coerced).__name__,
                        )
                        arguments[key] = coerced

        return await call_next(context)

    async def on_read_resource(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[ReadResourceContents]],
    ) -> Sequence[ReadResourceContents]:
        """Pass-through for resource reads (no coercion needed)."""
        return await call_next(context)

    async def on_get_prompt(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, GetPromptResult],
    ) -> GetPromptResult:
        """Pass-through for prompt gets (no coercion needed)."""
        return await call_next(context)


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.
    
    Middleware order matters - they execute in the order added:
    1. Error Handling - catches and transforms errors first
    2. JSON Coercion - coerces stringified JSON/YAML arguments
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
    
    # 2. JSON Coercion - Parse stringified JSON/YAML before Pydantic validation
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
