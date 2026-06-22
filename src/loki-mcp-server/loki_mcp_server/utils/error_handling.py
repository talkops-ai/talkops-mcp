"""Generic error boundary decorator for MCP tool functions.

Converts known exceptions into structured JSON responses that
AI agents can read and self-correct from, instead of opaque
"Internal error: ..." messages that break the agent cascade.

This is the single point of exception-to-response translation
for ALL tool functions — DRY, generic, and automatically applied
to every tool via BaseTool.

Design principles:
  - Catch at the tool boundary, NOT in the service layer
  - Service layer raises faithfully (LokiQueryError, etc.)
  - This decorator translates to structured JSON
  - Unknown exceptions re-raise (let FastMCP handle them)
"""

import functools
import logging
from typing import Any, Callable, Dict, TypeVar

from loki_mcp_server.exceptions import (
    LokiConnectionError,
    LokiQueryError,
    LokiQueryTooExpensiveError,
    LokiResourceNotFoundError,
    LokiValidationError,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def tool_error_boundary(func: F) -> F:
    """Decorator that catches known exceptions and returns structured errors.

    Wraps an async tool function so that recoverable errors are
    returned as JSON dicts (with ``error``, ``error_type``, and
    ``suggestion`` keys) instead of raising exceptions.  This lets
    the AI agent read the error and self-correct the query.

    Exception mapping:
      - LokiValidationError → error_type: "validation_error"
      - LokiQueryError      → error_type: "query_error"
      - LokiConnectionError → error_type: "connection_error"
      - LokiQueryTooExpensiveError → error_type: "query_too_expensive"
      - LokiResourceNotFoundError  → error_type: "not_found"

    Any other exception is NOT caught — it re-raises so FastMCP
    can handle it with its standard masking logic.

    Returns:
        Decorated async function with the same signature.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except LokiValidationError as exc:
            logger.warning("Validation error in tool '%s': %s", func.__name__, exc)
            return _error_response(
                error=str(exc),
                error_type="validation_error",
                suggestion=(
                    "LogQL queries MUST start with a stream selector "
                    "wrapped in curly braces: {label=\"value\"}. "
                    "Example: {service_name=\"my-service\"} "
                    "NOT service_name=\"my-service\". "
                    "Time expressions must be RFC3339 "
                    "(e.g., '2024-01-01T00:00:00Z') or relative "
                    "(e.g., 'now-1h')."
                ),
            )
        except LokiQueryError as exc:
            logger.warning("Query error in tool '%s': %s", func.__name__, exc)
            return _error_response(
                error=str(exc),
                error_type="query_error",
                suggestion=(
                    "Check LogQL syntax. Ensure selectors use "
                    "valid operators (=, !=, =~, !~), pipes are "
                    "followed by a valid stage (json, logfmt, "
                    "line_format, etc.), and string literals are quoted."
                ),
            )
        except LokiQueryTooExpensiveError as exc:
            logger.warning("Expensive query in tool '%s': %s", func.__name__, exc)
            return _error_response(
                error=str(exc),
                error_type="query_too_expensive",
                suggestion=(
                    "Narrow the time range, add more label selectors, "
                    "or use get_query_stats first to estimate cost."
                ),
            )
        except LokiResourceNotFoundError as exc:
            logger.warning("Not found in tool '%s': %s", func.__name__, exc)
            return _error_response(
                error=str(exc),
                error_type="not_found",
                suggestion=(
                    "The requested Loki endpoint was not found. "
                    "This may indicate a disabled feature or "
                    "incorrect Loki version."
                ),
            )
        except LokiConnectionError as exc:
            logger.error("Connection error in tool '%s': %s", func.__name__, exc)
            return _error_response(
                error=str(exc),
                error_type="connection_error",
                suggestion=(
                    "Cannot reach the Loki backend. "
                    "Verify LOKI_URL configuration and network connectivity."
                ),
            )

    # Strip the return annotation so FastMCP does NOT generate an outputSchema.
    # Without this, functools.wraps copies `-> Dict[str, Any]` from the wrapped
    # function, causing FastMCP to declare outputSchema on the tool and then
    # expect structuredContent in the MCP response — which the middleware stack
    # never produces, resulting in:
    #   RuntimeError: Tool X has an output schema but did not return structured content
    wrapper.__annotations__.pop("return", None)

    return wrapper  # type: ignore[return-value]


def _error_response(
    *,
    error: str,
    error_type: str,
    suggestion: str,
) -> Dict[str, Any]:
    """Build a standardized error response dict.

    Args:
        error: Human-readable error message.
        error_type: Machine-readable error category.
        suggestion: Actionable guidance for the AI to self-correct.

    Returns:
        Structured error dict with 'success', 'error', 'error_type',
        and 'suggestion' keys.
    """
    return {
        "success": False,
        "error": error,
        "error_type": error_type,
        "suggestion": suggestion,
    }
