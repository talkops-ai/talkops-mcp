"""Exception module."""

from loki_mcp_server.exceptions.custom import (
    LokiConnectionError,
    LokiQueryError,
    LokiQueryTooExpensiveError,
    LokiResourceError,
    LokiResourceNotFoundError,
    LokiValidationError,
)

__all__ = [
    "LokiQueryError",
    "LokiConnectionError",
    "LokiResourceError",
    "LokiResourceNotFoundError",
    "LokiValidationError",
    "LokiQueryTooExpensiveError",
]
