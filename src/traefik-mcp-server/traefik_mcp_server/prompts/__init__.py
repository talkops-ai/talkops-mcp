"""Prompts module for Traefik MCP Server."""

from typing import Dict, Any, List

from traefik_mcp_server.prompts.registry import PromptRegistry
from traefik_mcp_server.prompts.base import BasePrompt
from traefik_mcp_server.prompts.nginx_to_traefik_migration import NginxToTraefikMigrationPrompts

__all__ = [
    'initialize_prompts',
    'PromptRegistry',
    'BasePrompt',
    'NginxToTraefikMigrationPrompts',
]


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize all prompts and register them with the registry.
    
    Args:
        service_locator: Dictionary containing service instances
        
    Returns:
        Configured PromptRegistry
    """
    registry = PromptRegistry(service_locator)
    
    # Initialize prompt categories
    prompts: List[BasePrompt] = [
        NginxToTraefikMigrationPrompts(service_locator),
    ]
    
    # Add to registry
    for prompt in prompts:
        registry.register_prompt(prompt)
        
    return registry
