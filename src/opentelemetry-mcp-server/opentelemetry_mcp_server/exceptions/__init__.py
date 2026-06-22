"""Exception module."""

from opentelemetry_mcp_server.exceptions.custom import (
    OtelConfigParseError,
    OtelConnectionError,
    OtelOperationError,
    OtelResourceError,
    OtelResourceNotFoundError,
    OtelValidationError,
)

__all__ = [
    "OtelOperationError",
    "OtelResourceError",
    "OtelResourceNotFoundError",
    "OtelValidationError",
    "OtelConnectionError",
    "OtelConfigParseError",
]
