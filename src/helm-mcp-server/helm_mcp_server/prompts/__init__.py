"""Prompts module initialization."""

from typing import Dict, Any
from helm_mcp_server.prompts.registry import PromptRegistry
from helm_mcp_server.prompts.installation_prompts import InstallationPrompts
from helm_mcp_server.prompts.troubleshooting_prompts import TroubleshootingPrompts
from helm_mcp_server.prompts.security_prompts import SecurityPrompts
from helm_mcp_server.prompts.upgrade_prompts import UpgradePrompts
from helm_mcp_server.prompts.rollback_prompts import RollbackPrompts
from helm_mcp_server.prompts.workflow_prompts import WorkflowPrompts


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize all prompt modules.
    
    Args:
        service_locator: Dictionary of services
    
    Returns:
        Prompt registry with all prompts registered
    """
    registry = PromptRegistry()
    
    # Register prompt groups
    registry.register_prompt(InstallationPrompts(service_locator))
    registry.register_prompt(TroubleshootingPrompts(service_locator))
    registry.register_prompt(SecurityPrompts(service_locator))
    registry.register_prompt(UpgradePrompts(service_locator))
    registry.register_prompt(RollbackPrompts(service_locator))
    registry.register_prompt(WorkflowPrompts(service_locator))
    
    return registry

