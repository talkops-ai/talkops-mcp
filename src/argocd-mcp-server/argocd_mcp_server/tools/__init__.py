from .base import BaseTool
from .registry import ToolRegistry
from .application_manager import ApplicationManagerTools
from .deployment_executor import DeploymentExecutorTools
from .repository_mgmt import RepositoryManagementTools, ProjectManagementTools

__all__ = ["BaseTool", "ToolRegistry", "initialize_tools"]


def initialize_tools(service_locator) -> ToolRegistry:
    """Initialize and register all tools.
    
    Args:
        service_locator: Dictionary of services
    
    Returns:
        Configured ToolRegistry
    """
    registry = ToolRegistry(service_locator)
    
    # Register all tool groups
    registry.register_tool(ApplicationManagerTools(service_locator))
    registry.register_tool(DeploymentExecutorTools(service_locator))
    registry.register_tool(RepositoryManagementTools(service_locator))
    registry.register_tool(ProjectManagementTools(service_locator))
    
    return registry

