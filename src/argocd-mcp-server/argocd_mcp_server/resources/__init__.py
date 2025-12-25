from .base import BaseResource
from .registry import ResourceRegistry
from .argocd_resources import ArgoCDResources

__all__ = ["BaseResource", "ResourceRegistry", "ArgoCDResources", "initialize_resources"]


def initialize_resources(service_locator) -> ResourceRegistry:
    """Initialize and register all resources.
    
    Args:
        service_locator: Dictionary of services
    
    Returns:
        Configured ResourceRegistry
    """
    registry = ResourceRegistry(service_locator)
    
    # Register all resources
    registry.register_resource(ArgoCDResources(service_locator))
    
    return registry

