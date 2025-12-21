"""Custom exceptions for Helm MCP server.

Following FastMCP exceptions from:
https://gofastmcp.com/python-sdk/fastmcp-exceptions
"""

from fastmcp.exceptions import (
    FastMCPError,
    ToolError,
    ResourceError,
    NotFoundError,
    ValidationError,
)


class HelmOperationError(ToolError):
    """Error during Helm operations.
    
    Inherits from ToolError for tool-related Helm operations.
    """
    pass


class KubernetesOperationError(ToolError):
    """Error during Kubernetes operations.
    
    Inherits from ToolError for tool-related Kubernetes operations.
    """
    pass


class HelmResourceError(ResourceError):
    """Error during Helm resource operations.
    
    Inherits from ResourceError for resource-related Helm operations.
    """
    pass


class HelmResourceNotFoundError(NotFoundError):
    """Error when a Helm resource is not found.
    
    Inherits from NotFoundError for resource not found scenarios.
    """
    pass


class HelmValidationError(ValidationError):
    """Error validating Helm chart parameters or values.
    
    Inherits from ValidationError for validation-related errors.
    """
    pass

