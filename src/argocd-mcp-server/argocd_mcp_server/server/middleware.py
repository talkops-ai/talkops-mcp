"""Middleware setup for FastMCP server.

Includes ``JsonCoercionMiddleware`` — a defensive middleware that
auto-parses stringified JSON/YAML tool-call arguments before Pydantic
validation. This prevents failures when LLM agents send ``dict``
or ``list`` parameters as serialised strings (a known MCP ecosystem issue).
"""

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
    CallToolSettings,
    ReadResourceSettings,
)
from fastmcp.tools.tool import ToolResult
from argocd_mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)


class JsonCoercionMiddleware(Middleware):
    """Auto-coerce stringified JSON/YAML arguments to native objects.

    Many LLM agents send ``dict`` or ``list`` parameters as JSON strings
    or YAML strings instead of proper JSON objects. FastMCP's Pydantic
    validation rejects these **before** tool code runs, so the only way
    to fix it transparently is in middleware.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        """Coerce string arguments to dicts/lists before validation."""
        args = context.message.arguments
        if args:
            coerced_keys: list[str] = []
            for key, value in list(args.items()):
                if isinstance(value, str):
                    parsed = self._try_parse(value)
                    if parsed is not value:  # identity check — only update if changed
                        args[key] = parsed
                        coerced_keys.append(key)

            if coerced_keys:
                logger.info(
                    "Coerced stringified arguments to native objects: %s (tool=%s)",
                    coerced_keys,
                    context.message.name,
                )

        return await call_next(context)

    @staticmethod
    def _try_parse(value: str) -> Any:
        """Try JSON first (fast), then YAML (for structured config).

        Returns the original string unchanged if neither parser succeeds
        or if the result is not a dict/list (we don't want to coerce
        plain scalars like ``"true"`` -> ``True``).
        """
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

    Middleware order matters — they execute in the order added:
    1. Error Handling  — catches and transforms errors first
    2. JSON Coercion   — auto-parses stringified JSON/YAML arguments
    3. Caching         — caches discovery lists only (call_tool caching disabled
                         so state mutations and live status polling never return stale data)
    4. Logging         — tracks operations without logging raw payloads/secrets
    5. Timing          — measures performance
    """
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=False,
        transform_errors=True,
    ))

    mcp.add_middleware(JsonCoercionMiddleware())

    mcp.add_middleware(ResponseCachingMiddleware(
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        call_tool_settings=CallToolSettings(enabled=False),
        read_resource_settings=ReadResourceSettings(enabled=False),
    ))

    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=False,
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))

    mcp.add_middleware(TimingMiddleware())
