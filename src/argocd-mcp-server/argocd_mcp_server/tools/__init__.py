"""Tool registration entrypoint."""

from .application_manager import ApplicationManagerTools
from .base import BaseTool
from .deployment_executor import DeploymentExecutorTools
from .registry import ToolRegistry
from .repository_mgmt import ProjectManagementTools, RepositoryManagementTools

__all__ = ["BaseTool", "ToolRegistry", "initialize_tools"]


def initialize_tools(service_locator: dict) -> ToolRegistry:
    """Initialize and register all tool groups."""
    registry = ToolRegistry(service_locator)

    registry.register_tool(ApplicationManagerTools(service_locator))
    registry.register_tool(DeploymentExecutorTools(service_locator))
    registry.register_tool(RepositoryManagementTools(service_locator))
    registry.register_tool(ProjectManagementTools(service_locator))

    return registry
