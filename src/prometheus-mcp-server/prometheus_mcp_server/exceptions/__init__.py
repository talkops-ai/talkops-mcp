"""Exception module."""

from prometheus_mcp_server.exceptions.custom import (
    ConfirmationRequiredError,
    PrometheusConnectionError,
    PrometheusOperationError,
    PrometheusQueryError,
    PrometheusResourceError,
    PrometheusResourceNotFoundError,
    PrometheusValidationError,
    WriteAccessDeniedError,
)

__all__ = [
    "PrometheusOperationError",
    "PrometheusResourceError",
    "PrometheusResourceNotFoundError",
    "PrometheusValidationError",
    "PrometheusConnectionError",
    "PrometheusQueryError",
    "WriteAccessDeniedError",
    "ConfirmationRequiredError",
]
