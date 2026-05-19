"""Tools module initialization for Argo Rollout MCP Server.

Tool Categories:
1. Argo Rollouts: Rollout management and operations
2. Generators: Deployment ↔ Rollout conversion
3. Orchestration: (Future enhancement — orch_* tools are mockups, excluded from this release)
"""

from typing import Dict, Any
from argo_rollout_mcp_server.tools.registry import ToolRegistry

# Import tool groups
from argo_rollout_mcp_server.tools.argo.rollout_management import RolloutManagementTools
from argo_rollout_mcp_server.tools.argo.rollout_operations import RolloutOperationTools
# Orchestration tools (orch_*) — EXCLUDED: mockup implementations, moved to future enhancement
# from argo_rollout_mcp_server.tools.orchestration.intelligent_promotion import IntelligentPromotionTools
# from argo_rollout_mcp_server.tools.orchestration.cost_aware import CostAwareTools
# from argo_rollout_mcp_server.tools.orchestration.multi_cluster import MultiClusterTools
# from argo_rollout_mcp_server.tools.orchestration.policy_validation import PolicyValidationTools
# from argo_rollout_mcp_server.tools.orchestration.deployment_insights import DeploymentInsightsTools
# Generator tools (bridge between Deployments and Rollouts)
from argo_rollout_mcp_server.tools.generators.conversion_tools import GeneratorTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules.
    
    Args:
        service_locator: Dictionary of services containing:
            - argo_service: ArgoRollouts service for rollout operations
            - orchestration_service: Orchestration service (used when orch tools enabled)
            - generator_service: Generator service
            - config: ServerConfig instance
    
    Returns:
        ToolRegistry: Registry with all tools registered and ready
    """
    registry = ToolRegistry(service_locator)
    
    # Register Argo Rollouts tool groups
    registry.register_tool(RolloutManagementTools(service_locator))
    registry.register_tool(RolloutOperationTools(service_locator))
    
    # Orchestration tools (orch_*) excluded this release — mockup implementations
    # registry.register_tool(IntelligentPromotionTools(service_locator))
    # registry.register_tool(CostAwareTools(service_locator))
    # registry.register_tool(MultiClusterTools(service_locator))
    # registry.register_tool(PolicyValidationTools(service_locator))
    # registry.register_tool(DeploymentInsightsTools(service_locator))
    
    # Register Generator/Conversion tools (Argo-only subset)
    registry.register_tool(GeneratorTools(service_locator))
    
    return registry


__all__ = [
    'initialize_tools',
    'ToolRegistry',
]
