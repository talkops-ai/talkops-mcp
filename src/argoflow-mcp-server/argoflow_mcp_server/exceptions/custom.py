"""Custom exceptions for ArgoFlow MCP server.

This module defines custom exceptions for Argo Rollouts and Traefik operations,
following FastMCP exceptions from:
https://gofastmcp.com/python-sdk/fastmcp-exceptions
"""

from fastmcp.exceptions import (
    FastMCPError,
    ToolError,
    ResourceError,
    NotFoundError,
    ValidationError,
)


# =============================================================================
# ARGO ROLLOUTS EXCEPTIONS
# =============================================================================

class ArgoRolloutError(ToolError):
    """Base error for Argo Rollouts operations.
    
    Inherits from ToolError for tool-related Argo Rollouts operations.
    """
    pass


class RolloutNotFoundError(NotFoundError):
    """Error when a Rollout resource is not found.
    
    Raised when:
    - Rollout doesn't exist in specified namespace
    - Invalid rollout name provided
    
    Inherits from NotFoundError for resource not found scenarios.
    """
    pass


class RolloutStateError(ToolError):
    """Error when a Rollout is in an invalid state for the requested operation.
    
    Raised when:
    - Attempting to promote a rollout that's not paused
    - Trying to abort a rollout that's already completed
    - Operation not supported for current rollout phase
    
    Inherits from ToolError for state-related errors.
    """
    pass


class RolloutPromotionError(ToolError):
    """Error during rollout promotion operations.
    
    Raised when:
    - Promotion fails due to invalid step index
    - Cannot promote past final step
    - Promotion blocked by analysis failure
    
    Inherits from ToolError for promotion-specific errors.
    """
    pass


class AnalysisTemplateError(ToolError):
    """Error during Analysis Template operations.
    
    Raised when:
    - Analysis template creation fails
    - Invalid metrics configuration
    - Prometheus connectivity issues
    - Analysis run failures
    
    Inherits from ToolError for analysis-related errors.
    """
    pass


class RolloutStrategyError(ValidationError):
    """Error validating rollout strategy configuration.
    
    Raised when:
    - Invalid canary steps configuration
    - Mismatched blue-green service names
    - Invalid traffic routing configuration
    - Weights don't sum to 100
    
    Inherits from ValidationError for validation-related errors.
    """
    pass


class RolloutAbortError(ToolError):
    """Error during rollout abort operations.
    
    Raised when:
    - Abort operation fails
    - Cannot rollback to stable version
    - Rollout already aborted
    
    Inherits from ToolError for abort-specific errors.
    """
    pass


class RolloutHistoryError(ResourceError):
    """Error retrieving rollout history or audit trail.
    
    Raised when:
    - Cannot fetch rollout conditions
    - History data unavailable
    - Corrupted rollout status
    
    Inherits from ResourceError for resource-related history errors.
    """
    pass


# =============================================================================
# TRAEFIK TRAFFIC MANAGER EXCEPTIONS
# =============================================================================

class TraefikOperationError(ToolError):
    """Base error for Traefik operations.
    
    Inherits from ToolError for tool-related Traefik operations.
    """
    pass


class TraefikRouteNotFoundError(NotFoundError):
    """Error when a Traefik route is not found.
    
    Raised when:
    - IngressRoute doesn't exist
    - TraefikService not found
    - Invalid route name provided
    
    Inherits from NotFoundError for route not found scenarios.
    """
    pass


class TraefikServiceError(ToolError):
    """Error during TraefikService operations.
    
    Raised when:
    - TraefikService creation fails
    - Invalid weighted round robin configuration
    - Mirroring configuration errors
    - Service reference errors
    
    Inherits from ToolError for TraefikService-specific errors.
    """
    pass


class TraefikWeightError(ValidationError):
    """Error validating traffic weight configuration.
    
    Raised when:
    - Weights don't sum to valid total
    - Negative weights provided
    - Weight percentage out of range (0-100)
    - Invalid weight distribution
    
    Inherits from ValidationError for weight validation errors.
    """
    pass


class TraefikMiddlewareError(ToolError):
    """Error during Middleware operations.
    
    Raised when:
    - Middleware creation fails
    - Invalid rate limit configuration
    - Circuit breaker expression errors
    - Middleware not applied correctly
    
    Inherits from ToolError for middleware-specific errors.
    """
    pass


class TraefikRouteConfigError(ValidationError):
    """Error validating route configuration.
    
    Raised when:
    - Invalid hostname pattern
    - Missing required services
    - Invalid entry points
    - Route match expression errors
    
    Inherits from ValidationError for route configuration errors.
    """
    pass


class TraefikMirroringError(ToolError):
    """Error during traffic mirroring operations.
    
    Raised when:
    - Mirroring service creation fails
    - Invalid mirror percentage (not 0-100)
    - Mirror service not found
    - Mirroring conflicts with weighted routing
    
    Inherits from ToolError for mirroring-specific errors.
    """
    pass


class TraefikCircuitBreakerError(ToolError):
    """Error during circuit breaker operations.
    
    Raised when:
    - Invalid circuit breaker expression
    - Threshold validation fails
    - Circuit breaker triggered unexpectedly
    - Unknown trigger type
    
    Inherits from ToolError for circuit breaker errors.
    """
    pass


class TraefikAnomalyError(ResourceError):
    """Error during traffic anomaly detection.
    
    Raised when:
    - Cannot fetch traffic metrics
    - Anomaly detection algorithm fails
    - Missing monitoring data
    - Prometheus query errors
    
    Inherits from ResourceError for anomaly detection errors.
    """
    pass


# =============================================================================
# KUBERNETES OPERATIONS EXCEPTIONS
# =============================================================================

class KubernetesOperationError(ToolError):
    """Error during Kubernetes API operations.
    
    Raised when:
    - Kubernetes API connectivity issues
    - API server unavailable
    - Authentication/authorization failures
    - Generic Kubernetes API errors
    
    Inherits from ToolError for Kubernetes-related operations.
    """
    pass


class KubernetesResourceError(ResourceError):
    """Error during Kubernetes resource operations.
    
    Raised when:
    - CRD not installed (Rollout, TraefikService, etc.)
    - Resource creation/deletion fails
    - Invalid resource specification
    - API version mismatch
    
    Inherits from ResourceError for Kubernetes resource errors.
    """
    pass


class KubernetesNamespaceError(ValidationError):
    """Error related to Kubernetes namespace operations.
    
    Raised when:
    - Namespace doesn't exist
    - Invalid namespace name
    - Permission denied for namespace
    - Namespace is being deleted
    
    Inherits from ValidationError for namespace validation errors.
    """
    pass


class KubernetesRBACError(ToolError):
    """Error related to Kubernetes RBAC/permissions.
    
    Raised when:
    - Insufficient permissions to perform operation
    - ServiceAccount missing required roles
    - RBAC policy denies access
    - ClusterRole/Role binding issues
    
    Inherits from ToolError for RBAC-related errors.
    """
    pass


class KubernetesPatchError(ToolError):
    """Error during Kubernetes resource patch operations.
    
    Raised when:
    - Strategic merge patch fails
    - JSON patch validation errors
    - Patch conflicts with existing state
    - Invalid patch content type
    
    Inherits from ToolError for patch-specific errors.
    """
    pass


# =============================================================================
# MONITORING AND METRICS EXCEPTIONS
# =============================================================================

class MetricsCollectionError(ResourceError):
    """Error during metrics collection operations.
    
    Raised when:
    - Prometheus unavailable
    - Invalid metric query
    - Metrics data missing or incomplete
    - Time series query timeout
    
    Inherits from ResourceError for metrics-related errors.
    """
    pass


class CostAnalyticsError(ResourceError):
    """Error during cost analytics operations.
    
    Raised when:
    - Cost calculation fails
    - Missing replica count data
    - Invalid cost parameters
    - Budget constraint violations
    
    Inherits from ResourceError for cost analytics errors.
    """
    pass


class HealthCheckError(ResourceError):
    """Error during cluster health check operations.
    
    Raised when:
    - Argo Rollouts controller not running
    - Traefik not installed
    - System component unhealthy
    - Etcd connectivity issues
    
    Inherits from ResourceError for health check errors.
    """
    pass


# =============================================================================
# WORKFLOW AND AUTOMATION EXCEPTIONS
# =============================================================================

class DeploymentWorkflowError(ToolError):
    """Error during automated deployment workflows.
    
    Raised when:
    - Canary deployment workflow fails
    - Blue-green promotion errors
    - Multi-cluster deployment failures
    - Workflow timeout
    
    Inherits from ToolError for workflow-related errors.
    """
    pass


class ProgressionError(ToolError):
    """Error during canary progression operations.
    
    Raised when:
    - Cannot advance to next step
    - Progression blocked by metrics
    - Step duration timeout
    - Invalid progression state
    
    Inherits from ToolError for progression-specific errors.
    """
    pass


class AutoRollbackError(ToolError):
    """Error during automatic rollback operations.
    
    Raised when:
    - Rollback operation fails
    - Cannot restore stable version
    - Rollback timeout
    - Rollback blocked by policy
    
    Inherits from ToolError for auto-rollback errors.
    """
    pass
