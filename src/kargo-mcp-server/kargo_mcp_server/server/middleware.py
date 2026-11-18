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
from kargo_mcp_server.config import ServerConfig


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
        call_next: CallNext[Any, Any],
    ) -> Any:
        """Coerce stringified JSON/YAML/bool arguments before tool execution."""
        arguments = getattr(context.message, "arguments", None)
        if arguments and isinstance(arguments, dict):
            for key, value in list(arguments.items()):
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


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.

    Security & correctness invariants:
    - Never leak stack tracebacks or raw Kargo payload secrets in logs.
    - Never cache call_tool or read_resource responses (live promotion/verification state changes every second; fixes B6).
    """
    # 1. Error Handling — never leak raw tracebacks to client
    mcp.add_middleware(
        ErrorHandlingMiddleware(
            include_traceback=False,
            transform_errors=True,
        )
    )

    # 2. JSON/YAML/Boolean Coercion
    mcp.add_middleware(JsonCoercionMiddleware())

    # 3. Response Caching — ONLY cache static catalog listings; NEVER cache live tool calls or resource reads
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

    # 4. Structured Logging — never log full payloads (may contain manifests/secrets)
    mcp.add_middleware(
        StructuredLoggingMiddleware(
            include_payloads=False,
            include_payload_length=True,
            estimate_payload_tokens=True,
        )
    )

    # 5. Timing
    mcp.add_middleware(TimingMiddleware())
