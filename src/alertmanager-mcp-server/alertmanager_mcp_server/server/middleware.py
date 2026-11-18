"""Middleware setup for Alertmanager FastMCP server."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Set

from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.caching import (
    CallToolSettings,
    ListResourcesSettings,
    ListToolsSettings,
    ReadResourceSettings,
    ResponseCachingMiddleware,
)
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.middleware.response_limiting import (
    ResponseLimitingMiddleware,
)
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.tools.base import ToolResult

from alertmanager_mcp_server.config import ServerConfig
from alertmanager_mcp_server.domain.matchers import (
    MatcherValidationError,
    parse_matcher_set,
)

logger = logging.getLogger(__name__)

# Fallback parameter classification when tool schema metadata is not available
_DEFAULT_STRUCTURED_PARAMS: frozenset[str] = frozenset(
    {"labels", "annotations", "label_filters", "matchers"}
)
_DEFAULT_DICT_ONLY_PARAMS: frozenset[str] = frozenset(
    {"labels", "annotations"}
)


def _extract_allowed_json_types(prop_schema: dict[str, Any]) -> Set[str]:
    """Extract allowed JSON Schema primitive/container types for a parameter."""
    allowed: Set[str] = set()
    if "type" in prop_schema:
        t = prop_schema["type"]
        if isinstance(t, str):
            allowed.add(t)
        elif isinstance(t, list):
            allowed.update(str(x) for x in t)
    for union_key in ("anyOf", "oneOf", "allOf"):
        sub_list = prop_schema.get(union_key)
        if isinstance(sub_list, list):
            for item in sub_list:
                if isinstance(item, dict):
                    allowed.update(_extract_allowed_json_types(item))
    return allowed


class JsonCoercionMiddleware(Middleware):
    """Schema-aware argument coercion middleware for FastMCP tools.

    Fixes two common LLM tool-calling quirks without corrupting string parameters:
    1. When a parameter expects `object` or `array` (`labels`, `annotations`,
       `label_filters`, `matchers`), keeps native `dict`/`list` intact and
       coerces JSON strings (`'{"env": "prod"}'`) or Alertmanager matcher sets
       (`'{env="prod"}'`) into structured Python objects.
    2. When a parameter expects `string` (`comment`, `created_by`, `starts_at`,
       `ends_at`, `reason`, etc.), NEVER parses strings with YAML/JSON (preserving
       colons in comments like `"JIRA-123: db failover"` and ISO timestamps).
    """

    def __init__(self, mcp: Optional[FastMCP] = None) -> None:
        super().__init__()
        self._mcp = mcp

    def _get_param_types(
        self, context: MiddlewareContext[Any], param_name: str
    ) -> Set[str]:
        """Resolve allowed JSON Schema types for `param_name` on the target tool."""
        mcp_instance = self._mcp
        if mcp_instance is None and context.fastmcp_context is not None:
            mcp_instance = context.fastmcp_context.fastmcp

        if mcp_instance is not None:
            try:
                tool_name = getattr(context.message, "name", None)
                # Inspect local provider components if accessible
                providers = getattr(mcp_instance, "_providers", [])
                for provider in providers:
                    components = getattr(provider, "_components", {})
                    for key, comp in components.items():
                        if key.startswith(f"tool:{tool_name}@") or getattr(
                            comp, "name", None
                        ) == tool_name:
                            params_schema = getattr(comp, "parameters", None)
                            if isinstance(params_schema, dict):
                                props = params_schema.get("properties", {})
                                if param_name in props and isinstance(
                                    props[param_name], dict
                                ):
                                    types = _extract_allowed_json_types(
                                        props[param_name]
                                    )
                                    if types:
                                        return types
            except Exception:
                pass

        if param_name in _DEFAULT_DICT_ONLY_PARAMS:
            return {"object"}
        if param_name in _DEFAULT_STRUCTURED_PARAMS:
            return {"object", "array", "string"}
        return {"string", "integer", "number", "boolean"}

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        """Coerce tool arguments based on target parameter schema."""
        args = context.message.arguments
        if args:
            coerced_keys: list[str] = []
            for key, value in list(args.items()):
                if value is None:
                    continue
                allowed_types = self._get_param_types(context, key)
                allows_structured = bool(
                    allowed_types & {"object", "array"}
                )

                if allows_structured:
                    if isinstance(value, str):
                        coerced = self._coerce_str_to_structured(
                            value, allowed_types
                        )
                        if coerced is not value:
                            args[key] = coerced
                            coerced_keys.append(key)
                    # Native dict / list are preserved as-is!
                else:
                    # Parameter only accepts scalar/string types.
                    # Never YAML/JSON-parse string values!
                    if isinstance(value, dict) and "string" in allowed_types:
                        if len(value) == 1 and list(value.values())[0] is None:
                            args[key] = str(list(value.keys())[0])
                        elif len(value) == 0:
                            args[key] = "{}"
                        else:
                            args[key] = json.dumps(value)
                        coerced_keys.append(key)

            if coerced_keys:
                logger.debug(
                    "Coerced structured arguments for %s: %s",
                    context.message.name,
                    coerced_keys,
                )

        return await call_next(context)

    @staticmethod
    def _coerce_str_to_structured(
        value: str, allowed_types: Set[str]
    ) -> Any:
        stripped = value.strip()
        if not stripped:
            return value

        # 1. Try strict JSON parsing for object or array literals
        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and "object" in allowed_types:
                    return parsed
                if isinstance(parsed, list) and "array" in allowed_types:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        # 2. If it's a braced Alertmanager selector `{env="prod", service="api"}`
        #    and the parameter does NOT accept raw `string` (only object/array),
        #    parse via matcher grammar
        if (
            "string" not in allowed_types
            and stripped.startswith("{")
            and stripped.endswith("}")
        ):
            try:
                compiled = parse_matcher_set(stripped)
                if (
                    "object" in allowed_types
                    and "array" not in allowed_types
                    and all(m.is_equal and not m.is_regex for m in compiled)
                ):
                    return {m.name: m.value for m in compiled}
                if "array" in allowed_types:
                    return [m.to_api_dict() for m in compiled]
                if "object" in allowed_types:
                    return {
                        m.name: (
                            m.value
                            if (m.is_equal and not m.is_regex)
                            else f"{m.operator}{m.value}"
                        )
                        for m in compiled
                    }
            except MatcherValidationError:
                pass

        return value


def setup_middleware(mcp: FastMCP, config: ServerConfig) -> None:
    """Configure middleware stack for the Alertmanager FastMCP server."""
    # 1. Error Handling (preserve FastMCP ToolError so MCP returns isError=True)
    mcp.add_middleware(
        ErrorHandlingMiddleware(
            include_traceback=False,
            transform_errors=False,
        )
    )

    # 2. Response Limiting
    mcp.add_middleware(
        ResponseLimitingMiddleware(
            max_size=100_000,
        )
    )

    # 3. Rate Limiting
    mcp.add_middleware(
        RateLimitingMiddleware(
            max_requests_per_second=10.0,
            burst_capacity=20,
            global_limit=True,
        )
    )

    # 4. Schema-Aware JSON Coercion
    mcp.add_middleware(JsonCoercionMiddleware(mcp=mcp))

    # 5. Caching (cache tool/resource discovery lists; keep live resource reads uncached)
    mcp.add_middleware(
        ResponseCachingMiddleware(
            list_tools_settings=ListToolsSettings(ttl=300, enabled=True),
            list_resources_settings=ListResourcesSettings(ttl=300, enabled=True),
            call_tool_settings=CallToolSettings(ttl=0, enabled=False),
            read_resource_settings=ReadResourceSettings(ttl=0, enabled=False),
        )
    )

    # 6. Structured Logging (payload logging gated by MCP_LOG_PAYLOADS)
    mcp.add_middleware(
        StructuredLoggingMiddleware(
            include_payloads=config.log_payloads,
            include_payload_length=True,
            estimate_payload_tokens=True,
        )
    )

    # 7. Timing
    mcp.add_middleware(TimingMiddleware())
