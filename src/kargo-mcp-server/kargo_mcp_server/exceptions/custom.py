"""Custom exceptions for Kargo MCP server.

Following FastMCP exception hierarchy from:
https://gofastmcp.com/python-sdk/fastmcp-exceptions
"""

from fastmcp.exceptions import (
    ToolError,
    ResourceError,
    NotFoundError,
    ValidationError,
)


class KargoOperationError(ToolError):
    """Error during Kargo tool operations.

    Inherits from ToolError for tool-related Kargo API failures.
    """
    pass


class KargoResourceError(ResourceError):
    """Error during Kargo resource operations.

    Inherits from ResourceError for resource-related failures.
    """
    pass


class KargoResourceNotFoundError(NotFoundError):
    """Error when a Kargo resource is not found.

    Inherits from NotFoundError for 404 scenarios.
    """
    pass


class KargoValidationError(ValidationError):
    """Error validating Kargo parameters or specs.

    Inherits from ValidationError for input validation failures.
    """
    pass


class KargoAuthError(ToolError):
    """Error during Kargo authentication.

    Raised when admin login fails or tokens are missing/expired.
    """
    pass
