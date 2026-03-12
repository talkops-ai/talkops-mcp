"""Custom exceptions for Argo Rollout MCP server.

This module defines custom exceptions for Argo Rollouts operations,
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
    """Base error for Argo Rollouts operations."""
    pass


class RolloutNotFoundError(NotFoundError):
    """Error when a Rollout resource is not found."""
    pass


class RolloutStateError(ToolError):
    """Error when a Rollout is in an invalid state for the requested operation."""
    pass


class RolloutPromotionError(ToolError):
    """Error during rollout promotion operations."""
    pass


class AnalysisTemplateError(ToolError):
    """Error during Analysis Template operations."""
    pass


class RolloutStrategyError(ValidationError):
    """Error validating rollout strategy configuration."""
    pass


class RolloutAbortError(ToolError):
    """Error during rollout abort operations."""
    pass


class RolloutHistoryError(ResourceError):
    """Error retrieving rollout history or audit trail."""
    pass


# =============================================================================
# KUBERNETES OPERATIONS EXCEPTIONS
# =============================================================================

class KubernetesOperationError(ToolError):
    """Error during Kubernetes API operations."""
    pass


class KubernetesResourceError(ResourceError):
    """Error during Kubernetes resource operations."""
    pass


class KubernetesNamespaceError(ValidationError):
    """Error related to Kubernetes namespace operations."""
    pass


class KubernetesRBACError(ToolError):
    """Error related to Kubernetes RBAC/permissions."""
    pass


class KubernetesPatchError(ToolError):
    """Error during Kubernetes resource patch operations."""
    pass


# =============================================================================
# MONITORING AND METRICS EXCEPTIONS
# =============================================================================

class MetricsCollectionError(ResourceError):
    """Error during metrics collection operations."""
    pass


class CostAnalyticsError(ResourceError):
    """Error during cost analytics operations."""
    pass


class HealthCheckError(ResourceError):
    """Error during cluster health check operations."""
    pass


# =============================================================================
# WORKFLOW AND AUTOMATION EXCEPTIONS
# =============================================================================

class DeploymentWorkflowError(ToolError):
    """Error during automated deployment workflows."""
    pass


class ProgressionError(ToolError):
    """Error during canary progression operations."""
    pass


class AutoRollbackError(ToolError):
    """Error during automatic rollback operations."""
    pass
