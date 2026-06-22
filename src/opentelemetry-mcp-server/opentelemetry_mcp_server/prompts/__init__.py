"""Prompts module initialization.

Creates and returns the PromptRegistry with all prompt packs registered.
"""

from typing import Any, Dict

from opentelemetry_mcp_server.prompts.registry import PromptRegistry
from opentelemetry_mcp_server.prompts.otel_prompts import (
    GovernancePrompts,
    InvestigationPrompts,
    OnboardingPrompts,
    SamplingPrompts,
    SecurityPrompts,
)


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize all prompts and return the registry.

    Args:
        service_locator: Service locator dict with dependencies.

    Returns:
        Populated PromptRegistry.
    """
    registry = PromptRegistry()

    registry.register_prompt(OnboardingPrompts(service_locator))
    registry.register_prompt(InvestigationPrompts(service_locator))
    registry.register_prompt(GovernancePrompts(service_locator))
    registry.register_prompt(SamplingPrompts(service_locator))
    registry.register_prompt(SecurityPrompts(service_locator))

    return registry
