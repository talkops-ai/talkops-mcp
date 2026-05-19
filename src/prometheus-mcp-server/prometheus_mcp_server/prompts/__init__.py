"""Prompts module initialization."""

from typing import Any, Dict
from prometheus_mcp_server.prompts.registry import PromptRegistry
from prometheus_mcp_server.prompts.onboarding_prompts import OnboardingPrompts
from prometheus_mcp_server.prompts.troubleshooting_prompts import TroubleshootingPrompts
from prometheus_mcp_server.prompts.query_prompts import QueryPrompts
from prometheus_mcp_server.prompts.rule_prompts import RulePrompts


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize all prompt modules."""
    registry = PromptRegistry()

    registry.register_prompt(OnboardingPrompts(service_locator))
    registry.register_prompt(TroubleshootingPrompts(service_locator))
    registry.register_prompt(QueryPrompts(service_locator))
    registry.register_prompt(RulePrompts(service_locator))

    return registry
