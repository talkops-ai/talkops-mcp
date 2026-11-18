"""Custom exceptions for Kargo MCP server."""

from typing import Optional
from fastmcp.exceptions import (
    ToolError,
    ResourceError,
    NotFoundError,
    ValidationError,
)


class KargoApiError(Exception):
    """Raised for non-2xx responses from the Kargo REST API."""

    def __init__(
        self,
        status_code: int,
        message: str,
        body: Optional[str] = None,
    ) -> None:
        super().__init__(f"Kargo API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


# Backward-compatible alias used inside service/tests
ApiError = KargoApiError


class KargoOperationError(ToolError):
    """Error during Kargo tool operations."""

    pass


class KargoResourceError(ResourceError):
    """Error during Kargo resource operations."""

    pass


class KargoResourceNotFoundError(NotFoundError):
    """Error when a Kargo resource is not found (HTTP 404)."""

    pass


class KargoValidationError(ValidationError):
    """Error validating Kargo parameters or CRD specs."""

    pass


class KargoPermissionError(KargoOperationError):
    """Error when Kargo RBAC denies an operation (HTTP 401/403)."""

    pass


class KargoConflictError(KargoOperationError):
    """Error when a Kargo resource conflicts (HTTP 409)."""

    pass


class KargoPromotionError(KargoOperationError):
    """Error when a Kargo promotion or rollback fails."""

    pass


class KargoVerificationError(KargoOperationError):
    """Error when a Kargo stage verification fails or cannot be triggered."""

    pass
