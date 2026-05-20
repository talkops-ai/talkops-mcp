"""Custom exceptions for Alertmanager MCP server."""

from fastmcp.exceptions import NotFoundError, ResourceError, ToolError, ValidationError


class AlertmanagerOperationError(ToolError):
    """Error during Alertmanager tool operations."""
    pass


class AlertmanagerResourceError(ResourceError):
    """Error during Alertmanager resource operations."""
    pass


class AlertmanagerNotFoundError(NotFoundError):
    """Error when an Alertmanager resource is not found."""
    pass


class AlertmanagerValidationError(ValidationError):
    """Error validating Alertmanager parameters."""
    pass


class AlertmanagerConnectionError(ToolError):
    """Error connecting to an Alertmanager backend."""
    pass


class SilenceSafetyError(ToolError):
    """Error when a silence operation violates safety guardrails."""
    pass
