"""Custom exceptions for Tempo MCP server.

Following FastMCP exception hierarchy from:
https://gofastmcp.com/python-sdk/fastmcp-exceptions
"""

from fastmcp.exceptions import (
    NotFoundError,
    ResourceError,
    ToolError,
    ValidationError,
)


class TempoOperationError(ToolError):
    """Error during Tempo tool operations.

    Inherits from ToolError for tool-related Tempo API failures.
    """

    pass


class TempoResourceError(ResourceError):
    """Error during Tempo resource operations.

    Inherits from ResourceError for resource-related failures.
    """

    pass


class TempoResourceNotFoundError(NotFoundError):
    """Error when a Tempo resource is not found.

    Inherits from NotFoundError for 404 scenarios (e.g., unknown backend, missing trace).
    """

    pass


class TempoValidationError(ValidationError):
    """Error validating Tempo parameters or queries.

    Inherits from ValidationError for input validation failures
    (e.g., empty search, missing time range, invalid scope).
    """

    pass


class TempoConnectionError(ToolError):
    """Error connecting to a Tempo backend.

    Raised when a backend is unreachable, times out, or returns unexpected responses.
    """

    pass


class TempoQueryError(ToolError):
    """Error during TraceQL query execution.

    Raised for TraceQL syntax errors, query timeouts, or backend query failures.
    """

    pass


class TempoTenantError(ToolError):
    """Error related to tenant scoping.

    Raised when a multi-tenant backend requires a tenant ID but none was provided,
    or when the tenant ID format is invalid.
    """

    pass
