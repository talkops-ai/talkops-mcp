"""Custom exceptions for the Loki MCP server.

Following FastMCP exception hierarchy from:
https://gofastmcp.com/python-sdk/fastmcp-exceptions
"""

from fastmcp.exceptions import (
    NotFoundError,
    ResourceError,
    ToolError,
    ValidationError,
)


class LokiQueryError(ToolError):
    """Error during Loki query execution.

    Raised for bad LogQL syntax, Loki server errors,
    or unexpected response shapes.
    """

    pass


class LokiConnectionError(ToolError):
    """Error connecting to the Loki HTTP API.

    Raised when Loki is unreachable, times out,
    or returns unexpected HTTP responses.
    """

    pass


class LokiResourceError(ResourceError):
    """Error during Loki resource operations.

    Inherits from ResourceError for resource-related failures.
    """

    pass


class LokiResourceNotFoundError(NotFoundError):
    """Error when a Loki resource is not found.

    Inherits from NotFoundError for 404 scenarios
    (e.g., unknown label name, missing series).
    """

    pass


class LokiValidationError(ValidationError):
    """Error validating Loki parameters or queries.

    Raised for invalid LogQL syntax, bad time ranges,
    high-cardinality labels in stream selectors, etc.
    """

    pass


class LokiQueryTooExpensiveError(ToolError):
    """Error when a query exceeds the configured cost threshold.

    Raised when index stats show the query would touch more
    bytes than the configured maximum (default 5 GB).
    """

    pass
