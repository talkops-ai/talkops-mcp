"""Custom exceptions for Kargo MCP server."""

from kargo_mcp_server.exceptions.custom import (
    ApiError,
    KargoApiError,
    KargoConflictError,
    KargoOperationError,
    KargoPermissionError,
    KargoPromotionError,
    KargoResourceError,
    KargoResourceNotFoundError,
    KargoValidationError,
    KargoVerificationError,
)

__all__ = [
    "ApiError",
    "KargoApiError",
    "KargoConflictError",
    "KargoOperationError",
    "KargoPermissionError",
    "KargoPromotionError",
    "KargoResourceError",
    "KargoResourceNotFoundError",
    "KargoValidationError",
    "KargoVerificationError",
]
