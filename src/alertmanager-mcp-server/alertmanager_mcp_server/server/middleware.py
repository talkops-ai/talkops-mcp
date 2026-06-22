"""Middleware setup for FastMCP server."""

from typing import Any
import json
import yaml
import logging

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

from alertmanager_mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)

class JsonCoercionMiddleware(Middleware):
    """Auto-coerce tool arguments to native objects or valid strings.

    Many LLM agents send ``dict`` or ``list`` parameters as JSON strings,
    or conversely, send TraceQL/LogQL queries (which start with `{`) as
    JSON objects instead of strings. FastMCP's Pydantic validation rejects
    these before tool code runs.

    This middleware intercepts every ``tools/call`` request and applies
    two-way coercion:
    1. String -> Dict/List (via JSON/YAML parsing)
    2. Dict -> String (fixing hallucinative queries like `{"{app=\\"foo\\"}": null}`)
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        """Coerce arguments before validation."""
        args = context.message.arguments
        if args:
            coerced_keys: list[str] = []
            for key, value in list(args.items()):
                if isinstance(value, str):
                    parsed = self._try_parse(value)
                    if parsed is not value:
                        args[key] = parsed
                        coerced_keys.append(key)
                elif isinstance(value, dict):
                    # Handle LLM hallucinative queries parsed as JSON objects
                    if len(value) == 1 and list(value.values())[0] is None:
                        args[key] = list(value.keys())[0]
                        coerced_keys.append(key)
                    elif len(value) == 0:
                        args[key] = "{}"
                        coerced_keys.append(key)
                    else:
                        args[key] = json.dumps(value)
                        coerced_keys.append(key)

            if coerced_keys:
                logger.info(
                    "Coerced arguments to bypass Pydantic errors: %s (tool=%s)",
                    coerced_keys,
                    context.message.name,
                )

        return await call_next(context)

    @staticmethod
    def _try_parse(value: str) -> Any:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        if ":" in value or "\n" in value:
            try:
                parsed = yaml.safe_load(value)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except yaml.YAMLError:
                pass

        return value


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.

    Middleware order:
    1. Error Handling - catches and transforms errors
    2. Response Limiting - prevents massive payloads from crashing context
    3. Rate Limiting - protects against abusive or runaway requests
    4. JSON Coercion - fixes Pydantic validation errors from LLM hallucinations
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

    # 4. JSON Coercion - fixes Pydantic validation errors from LLM hallucinations
    mcp.add_middleware(JsonCoercionMiddleware())

    # 5. Caching 
    mcp.add_middleware(ResponseCachingMiddleware(
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        call_tool_settings=CallToolSettings(ttl=0, enabled=False),
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
