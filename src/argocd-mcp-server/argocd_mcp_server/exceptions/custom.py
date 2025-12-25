"""Custom exceptions for ArgoCD MCP server.

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


class ToolExecutionError(ToolError):
    """Base exception for tool execution failures"""
    pass


class ArgoDBNotAvailable(ToolExecutionError):
    """ArgoCD server unavailable"""
    pass


class ApplicationNotFound(NotFoundError):
    """Application doesn't exist"""
    pass


class SyncOperationFailed(ToolExecutionError):
    """Sync operation failed"""
    pass


class ValidationFailed(ValidationError):
    """Pre-deployment validation failed"""
    pass


# Additional exceptions that might be useful based on functionality
class ArgoCDOperationError(ToolExecutionError):
    """Error during generic ArgoCD operations."""
    pass


class ArgoCDConnectionError(ToolExecutionError):
    """Error connecting to ArgoCD server."""
    pass


class KubernetesOperationError(ToolExecutionError):
    """Error during Kubernetes operations."""
    pass


class ArgoCDResourceError(ResourceError):
    """Error accessing ArgoCD resources."""
    pass


class ArgoCDNotFoundError(NotFoundError):
    """Error when an ArgoCD resource is not found (generic)."""
    pass


class SyncOperationError(ToolExecutionError):
    """Error during application sync operations (alias for SyncOperationFailed if needed or generic sync error)."""
    pass


class RolloutOperationError(ToolExecutionError):
    """Error during rollout operations."""
    pass


class ArgoCDValidationError(ValidationError):
    """Error validating application configuration (generic)."""
    pass
