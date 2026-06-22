"""Custom exceptions for the OpenTelemetry MCP server.

Following FastMCP exception hierarchy from:
https://gofastmcp.com/python-sdk/fastmcp-exceptions
"""

from fastmcp.exceptions import (
    NotFoundError,
    ResourceError,
    ToolError,
    ValidationError,
)


class OtelOperationError(ToolError):
    """Error during OpenTelemetry tool operations.

    Inherits from ToolError for tool-related OTel API failures.
    """

    pass


class OtelResourceError(ResourceError):
    """Error during OpenTelemetry resource operations.

    Inherits from ResourceError for resource-related failures.
    """

    pass


class OtelResourceNotFoundError(NotFoundError):
    """Error when an OpenTelemetry resource is not found.

    Inherits from NotFoundError for 404 scenarios
    (e.g., missing CRD, unknown collector).
    """

    pass


class OtelValidationError(ValidationError):
    """Error validating OpenTelemetry parameters or configs.

    Inherits from ValidationError for input validation failures.
    """

    pass


class OtelConnectionError(ToolError):
    """Error connecting to Kubernetes API or Target Allocator.

    Raised when a backend is unreachable, times out,
    or returns unexpected responses.
    """

    pass


class OtelConfigParseError(ToolError):
    """Error parsing OpenTelemetry Collector configuration YAML.

    Raised for malformed collector configs, missing required fields,
    or invalid pipeline definitions.
    """

    pass
