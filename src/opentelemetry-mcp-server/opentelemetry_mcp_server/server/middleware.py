"""Middleware setup for FastMCP server."""

import json
import logging
from typing import Any

import yaml

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext
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
from fastmcp.tools.base import ToolResult
from fastmcp.resources.base import ResourceResult
from fastmcp.prompts.base import PromptResult
from opentelemetry_mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)


class JsonCoercionMiddleware(Middleware):
    """Coerce stringified JSON/YAML arguments and boolean strings into native Python objects.

    LLM agents frequently send ``dict``, ``list``, or ``bool`` tool parameters as
    JSON/YAML strings or ``"true"``/``"false"`` literals. This middleware intercepts
    ``tools/call`` requests and parses those strings before Pydantic validation runs.
    """

    _STRUCTURAL_CHARS = frozenset("{[")
    _BOOL_MAP = {
        "true": True,
        "false": False,
    }

    @classmethod
    def _try_parse(cls, value: str) -> Any:
        """Try boolean, JSON, then YAML; return parsed obj or the original string."""
        stripped = value.strip()
        lowered = stripped.lower()
        if lowered in cls._BOOL_MAP:
            return cls._BOOL_MAP[lowered]

        if not stripped or stripped[0] not in cls._STRUCTURAL_CHARS:
            return value

        # Fast path: JSON
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Slow path: YAML (only when structural chars are present)
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
        """Coerce stringified JSON/YAML/bool arguments before tool execution."""
        arguments = getattr(context.message, "arguments", None)
        if arguments and isinstance(arguments, dict):
            for key, value in list(arguments.items()):
                # Do not coerce config_yaml into a dict when a string is expected
                if key == "config_yaml":
                    continue
                if isinstance(value, str) and value:
                    coerced = self._try_parse(value)
                    if coerced is not value:
                        logger.debug(
                            "JsonCoercionMiddleware: coerced arg '%s' from str -> %s",
                            key,
                            type(coerced).__name__,
                        )
                        arguments[key] = coerced

        return await call_next(context)

    async def on_read_resource(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ResourceResult],
    ) -> ResourceResult:
        return await call_next(context)

    async def on_get_prompt(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, PromptResult],
    ) -> PromptResult:
        return await call_next(context)


class RequestResponseTransformationMiddleware(Middleware):
    """Middleware for transforming requests and responses."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        return await call_next(context)

    async def on_read_resource(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ResourceResult],
    ) -> ResourceResult:
        return await call_next(context)

    async def on_get_prompt(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, PromptResult],
    ) -> PromptResult:
        return await call_next(context)


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.

    Security & correctness invariants:
    - Never leak raw stack tracebacks or unredacted Collector/K8s payload secrets in logs.
    - Never cache call_tool or read_resource responses so live cluster state is never stale.
    """
    # 1. Error Handling
    mcp.add_middleware(
        ErrorHandlingMiddleware(
            include_traceback=False,
            transform_errors=True,
        )
    )

    # 2. JSON/YAML/Boolean Coercion
    mcp.add_middleware(JsonCoercionMiddleware())

    # 3. Response Limiting
    mcp.add_middleware(
        ResponseLimitingMiddleware(
            max_size=100_000,
        )
    )

    # 4. Rate Limiting
    mcp.add_middleware(
        RateLimitingMiddleware(
            max_requests_per_second=10.0,
            burst_capacity=20,
            global_limit=True,
        )
    )

    # 5. Request/Response Transformation
    mcp.add_middleware(RequestResponseTransformationMiddleware())

    # 6. Caching — ONLY cache static catalog listings; NEVER cache live tool or resource reads
    mcp.add_middleware(
        ResponseCachingMiddleware(
            list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
            list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
            list_prompts_settings=ListPromptsSettings(ttl=300, enabled=False),
            call_tool_settings=CallToolSettings(enabled=False),
            read_resource_settings=ReadResourceSettings(enabled=False),
            get_prompt_settings=GetPromptSettings(enabled=False),
        )
    )

    # 7. Logging — never log full payloads (may contain exporter headers/tokens)
    mcp.add_middleware(
        StructuredLoggingMiddleware(
            include_payloads=False,
            include_payload_length=True,
            estimate_payload_tokens=True,
        )
    )

    # 8. Timing
    mcp.add_middleware(TimingMiddleware())
