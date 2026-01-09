"""Prompts module for ArgoFlow MCP Server.

This module provides MCP prompts for guided deployment workflows:
- Canary Deployment - Metrics-driven progressive traffic shift
- Blue-Green Deployment - Instant traffic switching
- Rolling Update - Standard Kubernetes pod-by-pod
- Multi-Cluster Canary - Sequential regional deployment
- Cost-Optimized Deployment - Budget-aware deployment
"""

from typing import Dict, Any
from argoflow_mcp_server.prompts.registry import PromptRegistry
from argoflow_mcp_server.prompts.canary_deployment import CanaryDeploymentPrompts
from argoflow_mcp_server.prompts.bluegreen_deployment import BlueGreenDeploymentPrompts
from argoflow_mcp_server.prompts.rolling_update import RollingUpdatePrompts
from argoflow_mcp_server.prompts.multicluster_canary import MultiClusterCanaryPrompts
from argoflow_mcp_server.prompts.cost_optimized import CostOptimizedDeploymentPrompts


__all__ = [
    'PromptRegistry',
    'CanaryDeploymentPrompts',
    'BlueGreenDeploymentPrompts',
    'RollingUpdatePrompts',
    'MultiClusterCanaryPrompts',
    'CostOptimizedDeploymentPrompts',
    'initialize_prompts',
]


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize and register all prompts.
    
    Args:
        service_locator: Dictionary containing services (argo_service, traefik_service, config)
    
    Returns:
        PromptRegistry with all prompts registered
    
    Example:
        >>> service_locator = {
        ...     'argo_service': argo_service,
        ...     'traefik_service': traefik_service,
        ...     'config': config
        ... }
        >>> registry = initialize_prompts(service_locator)
        >>> registry.register_all_prompts(mcp_instance)
    """
    registry = PromptRegistry(service_locator)
    
    # Register all prompt types
    registry.register_prompt(CanaryDeploymentPrompts(service_locator))
    registry.register_prompt(BlueGreenDeploymentPrompts(service_locator))
    registry.register_prompt(RollingUpdatePrompts(service_locator))
    registry.register_prompt(MultiClusterCanaryPrompts(service_locator))
    registry.register_prompt(CostOptimizedDeploymentPrompts(service_locator))
    
    return registry
