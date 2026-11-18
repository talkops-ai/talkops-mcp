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
from tempo_mcp_server.config import ServerConfig

# Keys that expect a TraceQL or raw log string rather than a JSON dict
_STRING_QUERY_KEYS = frozenset({"query", "q", "base_query", "selection", "log_line"})


class JsonCoercionMiddleware(Middleware):
    """Auto-coerce tool arguments to native objects or valid strings."""

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
                if isinstance(value, str) and key not in _STRING_QUERY_KEYS:
                    parsed = self._try_parse(value)
                    if parsed is not value:
                        args[key] = parsed
                        coerced_keys.append(key)
                elif isinstance(value, dict) and key in _STRING_QUERY_KEYS:
                    # Handle LLM hallucinative TraceQL queries parsed as JSON objects
                    if len(value) == 1 and list(value.values())[0] is None:
                        args[key] = list(value.keys())[0]
                        coerced_keys.append(key)
                    elif len(value) == 0:
                        args[key] = "{}"
                        coerced_keys.append(key)
                    else:
                        import json
                        args[key] = json.dumps(value)
                        coerced_keys.append(key)

            if coerced_keys:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    "Coerced arguments to bypass Pydantic errors: %s (tool=%s)",
                    coerced_keys,
                    context.message.name,
                )

        return await call_next(context)

    @staticmethod
    def _try_parse(value: str) -> Any:
        import json
        import yaml
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
    """Setup middleware for FastMCP server."""
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=False,
        transform_errors=True,
    ))

    mcp.add_middleware(ResponseLimitingMiddleware(
        max_size=config.response_size_hard_limit,
    ))

    mcp.add_middleware(RateLimitingMiddleware(
        max_requests_per_second=50.0,
        burst_capacity=100,
        global_limit=True,
    ))

    mcp.add_middleware(JsonCoercionMiddleware())

    mcp.add_middleware(ResponseCachingMiddleware(
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        call_tool_settings=CallToolSettings(ttl=0, enabled=False),
        read_resource_settings=ReadResourceSettings(ttl=30, enabled=True),
        get_prompt_settings=GetPromptSettings(ttl=3600, enabled=True),
    ))

    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=True,
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))

    mcp.add_middleware(TimingMiddleware())
