"""Resources module for Terraform MCP Server.

Provides MCP resources for operational insights:
- Knowledge graph statistics (chunk counts, embedding coverage)
- Server configuration summary (secrets redacted)
"""

from typing import Dict, Any, List

from terraform_mcp_server.resources.registry import ResourceRegistry
from terraform_mcp_server.resources.base import BaseResource
from terraform_mcp_server.resources.terraform_resources import TerraformResources

__all__ = [
    'initialize_resources',
    'ResourceRegistry',
    'BaseResource',
    'TerraformResources',
]


def initialize_resources(service_locator: Dict[str, Any]) -> ResourceRegistry:
    """Initialize all resources and register them with the registry.
    
    Args:
        service_locator: Dependency injection container
    
    Returns:
        Configured ResourceRegistry ready for register_all_resources()
    """
    registry = ResourceRegistry(service_locator)
    
    resources: List[BaseResource] = [
        TerraformResources(service_locator),
    ]
    
    for resource in resources:
        registry.register_resource(resource)
    
    return registry
