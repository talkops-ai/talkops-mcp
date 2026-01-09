"""Tools module initialization for ArgoFlow MCP Server.

This module provides centralized initialization and registration of all
tool categories for the ArgoFlow MCP server:

1. Argo Rollouts Tools - Manage progressive delivery and rollouts
2. Traefik Tools - Control traffic routing and canary deployments  
3. Orchestration Tools - Coordinate multi-service deployments

Tool Organization:
- argo/: Argo Rollouts deployment and management tools
- traefik/: Traefik traffic routing and middleware tools
- orchestration/: High-level deployment orchestration workflows
"""

from typing import Dict, Any
from argoflow_mcp_server.tools.registry import ToolRegistry

# Import tool groups
from argoflow_mcp_server.tools.argo.rollout_management import RolloutManagementTools
from argoflow_mcp_server.tools.argo.rollout_operations import RolloutOperationTools
from argoflow_mcp_server.tools.traefik.traffic_routing import TrafficRoutingTools
from argoflow_mcp_server.tools.traefik.middleware_management import MiddlewareTools
# Orchestration tools
from argoflow_mcp_server.tools.orchestration.intelligent_promotion import IntelligentPromotionTools
from argoflow_mcp_server.tools.orchestration.cost_aware import CostAwareTools
from argoflow_mcp_server.tools.orchestration.multi_cluster import MultiClusterTools
from argoflow_mcp_server.tools.orchestration.policy_validation import PolicyValidationTools
from argoflow_mcp_server.tools.orchestration.deployment_insights import DeploymentInsightsTools
# Generator tools (bridge between Deployments and Rollouts)
from argoflow_mcp_server.tools.generators.conversion_tools import GeneratorTools


def initialize_tools(service_locator: Dict[str, Any]) -> ToolRegistry:
    """Initialize all tool modules.
    
    Creates a ToolRegistry and registers all tool groups with it.
    Each tool group is a class that inherits from BaseTool and implements
    multiple related tools.
    
    Tool Categories:
    1. Argo Rollouts:
       - Rollout Management: Create, delete, update rollouts
       - Rollout Operations: Promote, abort, pause, resume, skip analysis
       - History & Status: Get status, history, traffic distribution
    
    2. Traefik Traffic Manager:
       - Routing: Create/update/delete weighted routes
       - Middleware: Rate limiting, circuit breakers, mirroring
       - Monitoring: Traffic distribution, anomaly detection
    
    3. Orchestration:
       - Deployment Workflows: Canary, blue-green, rolling updates
       - Multi-cluster: Cross-region deployments
       - Cost Management: Budget-aware deployments
    
    Args:
        service_locator: Dictionary of services containing:
            - argo_service: ArgoRollouts service for rollout operations
            - traefik_service: Traefik service for traffic management
            - k8s_service: Kubernetes service for cluster operations
            - validation_service: Input validation service
            - config: ServerConfig instance
    
    Returns:
        ToolRegistry: Registry with all tools registered and ready
        
    Example:
        service_locator = {
            'argo_service': argo_service,
            'traefik_service': traefik_service,
            'k8s_service': k8s_service,
            'validation_service': validation_service,
            'config': config
        }
        registry = initialize_tools(service_locator)
        registry.register_all_tools(mcp_instance)
    """
    registry = ToolRegistry(service_locator)
    
    # Register Argo Rollouts tool groups
    registry.register_tool(RolloutManagementTools(service_locator))
    registry.register_tool(RolloutOperationTools(service_locator))
    
    # Register Traefik tool groups
    registry.register_tool(TrafficRoutingTools(service_locator))
    registry.register_tool(MiddlewareTools(service_locator))
    
    # Register Orchestration tool groups
    registry.register_tool(IntelligentPromotionTools(service_locator))
    registry.register_tool(CostAwareTools(service_locator))
    registry.register_tool(MultiClusterTools(service_locator))
    registry.register_tool(PolicyValidationTools(service_locator))
    registry.register_tool(DeploymentInsightsTools(service_locator))
    
    # Register Generator/Conversion tools
    registry.register_tool(GeneratorTools(service_locator))
    
    return registry


__all__ = [
    'initialize_tools',
    'ToolRegistry',
]
