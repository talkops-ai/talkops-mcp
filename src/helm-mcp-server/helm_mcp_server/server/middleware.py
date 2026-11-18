"""Middleware setup for FastMCP execution server.

Includes:
- ErrorHandlingMiddleware: clean error transformation without tracebacks
- JsonCoercionMiddleware: auto-parses stringified JSON/YAML tool-call arguments
- ResponseCachingMiddleware: caches only static schema discovery (list_tools / list_resources);
  tool executions and live cluster resource reads are NEVER cached to prevent stale state
  or skipped mutations.
- StructuredLoggingMiddleware: payload logging disabled to prevent secret leakage in logs.
- TimingMiddleware: request execution latency tracking.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import yaml
from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.caching import (
    CallToolSettings,
    GetPromptSettings,
    ListPromptsSettings,
    ListResourcesSettings,
    ListToolsSettings,
    ReadResourceSettings,
    ResponseCachingMiddleware,
)
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.tools.tool import ToolResult
from helm_mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)


class JsonCoercionMiddleware(Middleware):
    """Auto-coerce stringified JSON/YAML arguments to native dicts/lists before Pydantic validation."""

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
                    if parsed is not value:
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
        """Try JSON first, then YAML (only for structured dict/list payloads)."""
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
    """Register middleware stack on the FastMCP server."""
    mcp.add_middleware(
        ErrorHandlingMiddleware(
            include_traceback=False,
            transform_errors=True,
        )
    )

    mcp.add_middleware(JsonCoercionMiddleware())

    # Never cache call_tool or read_resource — mutations and live cluster state must always execute
    mcp.add_middleware(
        ResponseCachingMiddleware(
            list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
            list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
            list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
            call_tool_settings=CallToolSettings(enabled=False),
            read_resource_settings=ReadResourceSettings(enabled=False),
            get_prompt_settings=GetPromptSettings(enabled=False),
        )
    )

    # Disable include_payloads so secrets in values/manifests are never written to logs
    mcp.add_middleware(
        StructuredLoggingMiddleware(
            include_payloads=False,
            include_payload_length=True,
            estimate_payload_tokens=True,
        )
    )

    mcp.add_middleware(TimingMiddleware())
