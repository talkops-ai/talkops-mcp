"""Custom exceptions for Alertmanager MCP server with model-directed recovery hints."""

from fastmcp.exceptions import NotFoundError, ResourceError, ToolError, ValidationError


class AlertmanagerOperationError(ToolError):
    """Error during Alertmanager tool operations."""


class AlertmanagerResourceError(ResourceError):
    """Error during Alertmanager resource operations."""


class AlertmanagerNotFoundError(NotFoundError, ToolError):
    """Error when an Alertmanager backend, alert fingerprint, or silence ID is not found."""


class AlertmanagerValidationError(ValidationError, ToolError):
    """Error validating Alertmanager parameters, matchers, or timestamps."""


class AlertmanagerConnectionError(ToolError):
    """Error connecting to an Alertmanager backend."""


class SilenceSafetyError(ToolError):
    """Error when a silence operation violates safety or governance policy (`SP001`–`SP009`)."""


class WriteAccessDeniedError(ToolError):
    """Error when a mutating operation is invoked while the server is in read-only mode."""


class ConfirmationRequiredError(ToolError):
    """Error when a high-blast-radius or destructive mutation requires explicit confirmation."""


__all__ = [
    "AlertmanagerConnectionError",
    "AlertmanagerNotFoundError",
    "AlertmanagerOperationError",
    "AlertmanagerResourceError",
    "AlertmanagerValidationError",
    "ConfirmationRequiredError",
    "SilenceSafetyError",
    "WriteAccessDeniedError",
]
