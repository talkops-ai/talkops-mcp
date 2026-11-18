"""Custom exceptions for Traefik MCP Server."""

from fastmcp.exceptions import (
    FastMCPError,
    ToolError,
    ResourceError,
    NotFoundError,
    ValidationError,
)


class TraefikOperationError(ToolError):
    """Base error for Traefik operations."""


class TraefikRouteNotFoundError(NotFoundError):
    """Error when a Traefik route or resource is not found."""


class TraefikServiceError(ToolError):
    """Error during TraefikService operations."""


class TraefikWeightError(ValidationError):
    """Error validating traffic weight configuration."""


class TraefikMiddlewareError(ToolError):
    """Error during Middleware operations."""


class TraefikRouteConfigError(ValidationError):
    """Error validating route configuration."""


class TraefikMirroringError(ToolError):
    """Error during traffic mirroring operations."""


class TraefikCircuitBreakerError(ToolError):
    """Error during circuit breaker operations."""


class TraefikTLSError(ToolError):
    """Error during TLSOption, TLSStore, or certificate operations."""


class TraefikSchemaGatingError(ValidationError):
    """Error when a requested field or middleware type is not supported by the installed Traefik CRD schema."""


class TraefikOwnershipError(ToolError):
    """Error when an object is owned by an external controller (e.g. Argo Rollouts or NGINX provider)."""


class TraefikReferentialIntegrityError(ValidationError):
    """Error when referenced Services, Middlewares, Secrets, or Transports are missing or invalid."""


class TraefikEmptyBackendError(ToolError):
    """Error when assigning positive traffic weight to a backend Service with zero ready endpoints."""


class TraefikSSRFBlockedError(ValidationError):
    """Error when an endpoint probe target host is not permitted by the SSRF hostname allowlist."""


class KubernetesOperationError(ToolError):
    """Error during Kubernetes API operations."""


class KubernetesResourceError(ResourceError):
    """Error during Kubernetes resource operations."""


class KubernetesNamespaceError(ValidationError):
    """Error related to Kubernetes namespace policy or existence."""


class KubernetesRBACError(ToolError):
    """Error related to Kubernetes RBAC/permissions."""


class KubernetesPatchError(ToolError):
    """Error during Kubernetes resource patch operations."""


class MetricsCollectionError(ResourceError):
    """Error during Prometheus metrics collection operations."""


class HealthCheckError(ResourceError):
    """Error during cluster or Traefik health check operations."""
