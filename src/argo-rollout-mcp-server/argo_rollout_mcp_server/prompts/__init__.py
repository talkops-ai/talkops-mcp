"""Prompts module for Argo Rollout MCP Server.

Provides AI agent guidance for progressive delivery workflows:
- Canary deployments
- Blue-Green deployments
- Standard rolling updates
- Cost-optimized scaling
- Multi-cluster global rollouts
- App onboarding (Deployment to Rollout conversion)
"""

from typing import Dict, Any
from argo_rollout_mcp_server.prompts.registry import PromptRegistry

from argo_rollout_mcp_server.prompts.canary_deployment import CanaryDeploymentPrompts
from argo_rollout_mcp_server.prompts.bluegreen_deployment import BlueGreenDeploymentPrompts
from argo_rollout_mcp_server.prompts.rolling_update import RollingUpdatePrompts
from argo_rollout_mcp_server.prompts.cost_optimized import CostOptimizedDeploymentPrompts
from argo_rollout_mcp_server.prompts.onboarding_deployment import OnboardingDeploymentPrompts
from argo_rollout_mcp_server.prompts.multicluster_canary import MultiClusterCanaryPrompts


__all__ = [
    'PromptRegistry',
    'initialize_prompts',
]


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize and register all prompts.
    
    Args:
        service_locator: Dictionary containing services
    
    Returns:
        PromptRegistry with all prompts registered
    """
    registry = PromptRegistry(service_locator)
    
    # Register Rollout-specific guided workflows
    registry.register_prompt(OnboardingDeploymentPrompts(service_locator))
    registry.register_prompt(CanaryDeploymentPrompts(service_locator))
    registry.register_prompt(BlueGreenDeploymentPrompts(service_locator))
    registry.register_prompt(RollingUpdatePrompts(service_locator))
    registry.register_prompt(CostOptimizedDeploymentPrompts(service_locator))
    registry.register_prompt(MultiClusterCanaryPrompts(service_locator))
    
    return registry
