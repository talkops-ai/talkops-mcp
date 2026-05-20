"""Custom exceptions for Prometheus MCP server.

Following FastMCP exception hierarchy from:
https://gofastmcp.com/python-sdk/fastmcp-exceptions
"""

from fastmcp.exceptions import (
    NotFoundError,
    ResourceError,
    ToolError,
    ValidationError,
)


class PrometheusOperationError(ToolError):
    """Error during Prometheus tool operations.

    Inherits from ToolError for tool-related Prometheus API failures.
    """
    pass


class PrometheusResourceError(ResourceError):
    """Error during Prometheus resource operations.

    Inherits from ResourceError for resource-related failures.
    """
    pass


class PrometheusResourceNotFoundError(NotFoundError):
    """Error when a Prometheus resource is not found.

    Inherits from NotFoundError for 404 scenarios (e.g., unknown backend).
    """
    pass


class PrometheusValidationError(ValidationError):
    """Error validating Prometheus parameters or queries.

    Inherits from ValidationError for input validation failures.
    """
    pass


class PrometheusConnectionError(ToolError):
    """Error connecting to a Prometheus backend.

    Raised when a backend is unreachable, times out, or returns unexpected responses.
    """
    pass


class PrometheusQueryError(ToolError):
    """Error during PromQL query execution.

    Raised for counter rule violations, query timeouts, or invalid PromQL.
    """
    pass
