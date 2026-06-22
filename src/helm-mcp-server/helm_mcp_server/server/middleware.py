"""Middleware setup for FastMCP server.

Includes ``JsonCoercionMiddleware`` — a defensive middleware that
auto-parses stringified JSON/YAML tool-call arguments before Pydantic
validation.  This prevents failures when LLM agents send ``dict``
parameters as serialised strings (a known MCP ecosystem issue).
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
    ListPromptsSettings,
    CallToolSettings,
    ReadResourceSettings,
    GetPromptSettings,
)
from fastmcp.tools.tool import ToolResult
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import GetPromptResult
from helm_mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON / YAML coercion middleware
# ---------------------------------------------------------------------------


class JsonCoercionMiddleware(Middleware):
    """Auto-coerce stringified JSON/YAML arguments to native objects.

    Many LLM agents send ``dict`` or ``list`` parameters as JSON strings
    or YAML strings instead of proper JSON objects.  FastMCP's Pydantic
    validation rejects these **before** tool code runs, so the only way
    to fix it transparently is in middleware.

    The middleware intercepts every ``tools/call`` request and attempts to
    parse any string-valued argument into a Python dict/list.  JSON is
    tried first (fast, no ambiguity), then YAML (for Helm-style values).

    Following the official FastMCP "Modifying Requests" pattern:
    https://gofastmcp.com/servers/middleware#modifying-requests
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
                    "Coerced stringified arguments to native objects: %s "
                    "(tool=%s)",
                    coerced_keys,
                    context.message.name,
                )

        return await call_next(context)

    @staticmethod
    def _try_parse(value: str) -> Any:
        """Try JSON first (fast), then YAML (for Helm values).

        Returns the original string unchanged if neither parser succeeds
        or if the result is not a dict/list (we don't want to coerce
        plain scalars like ``"true"`` → ``True``).
        """
        # --- JSON (fast path) ---
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # --- YAML (only when the string looks structured) ---
        # Heuristic: skip strings that are clearly not YAML maps/lists
        if ":" in value or "\n" in value:
            try:
                parsed = yaml.safe_load(value)
                if isinstance(parsed, (dict, list)):
                    return parsed
            except yaml.YAMLError:
                pass

        return value  # unchanged


# ---------------------------------------------------------------------------
# Middleware registration
# ---------------------------------------------------------------------------


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Setup middleware for FastMCP server.

    Middleware order matters — they execute in the order added:
    1. Error Handling  — catches and transforms errors first
    2. JSON Coercion   — auto-parses stringified JSON/YAML arguments
    3. Caching         — checks cache before execution
    4. Logging         — tracks all operations
    5. Timing          — measures performance

    Args:
        mcp: FastMCP server instance
        config: Server configuration
    """
    # 1. Error Handling — Provide consistent error responses
    # Set include_traceback=False to show clean error messages without stack traces
    mcp.add_middleware(ErrorHandlingMiddleware(
        include_traceback=False,
        transform_errors=True,
    ))

    # 2. JSON Coercion — Auto-parse stringified JSON/YAML tool-call arguments
    # Must run BEFORE caching and tool execution so Pydantic sees native objects.
    # This prevents the common LLM pattern of sending:
    #   "values": "{\"api\": {\"insecure\": true}}"  (JSON string)
    #   "values": "api:\n  insecure: true"           (YAML string)
    # instead of:
    #   "values": {"api": {"insecure": true}}         (native object)
    mcp.add_middleware(JsonCoercionMiddleware())

    # 3. Caching — Store frequently requested data to improve performance
    # IMPORTANT: Resource reads (helm://releases, kubernetes://*) and tool calls
    # return cluster state that changes on install/uninstall/upgrade.  Use short
    # TTLs (30s) so cache does not serve stale data after mutating operations.
    mcp.add_middleware(ResponseCachingMiddleware(
        # Cache list operations for 5 minutes (300 seconds)
        list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
        list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
        list_prompts_settings=ListPromptsSettings(ttl=300, enabled=True),
        # Short TTL for cluster-state: install/uninstall/upgrade invalidate cache
        call_tool_settings=CallToolSettings(ttl=30, enabled=True),
        read_resource_settings=ReadResourceSettings(ttl=30, enabled=True),
        # Prompts are static; longer TTL is fine
        get_prompt_settings=GetPromptSettings(ttl=3600, enabled=True),
    ))

    # 4. Logging and Monitoring — Track usage patterns and performance metrics
    mcp.add_middleware(StructuredLoggingMiddleware(
        include_payloads=True,
        include_payload_length=True,
        estimate_payload_tokens=True,
    ))

    # 5. Timing — Measure request execution time (part of monitoring)
    mcp.add_middleware(TimingMiddleware())
