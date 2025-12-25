from .base import BasePrompt
from .registry import PromptRegistry
from .deployment_workflows import ArgoCDPrompts
from .repository_workflows import RepositoryWorkflowPrompts

__all__ = ["BasePrompt", "PromptRegistry", "ArgoCDPrompts", "RepositoryWorkflowPrompts", "initialize_prompts"]


def initialize_prompts(service_locator) -> None:
    """Initialize and register all prompts.
    
    Args:
        service_locator: Dictionary of services
    
    Returns:
        Configured PromptRegistry
    """
    registry = PromptRegistry(service_locator)
    
    # Register all prompts
    registry.register_prompt(ArgoCDPrompts(service_locator))
    registry.register_prompt(RepositoryWorkflowPrompts(service_locator))
    
    return registry

