"""Prompts module initialization."""

from typing import Dict, Any
from kargo_mcp_server.prompts.registry import PromptRegistry
from kargo_mcp_server.prompts.promotion_prompts import PromotionPrompts
from kargo_mcp_server.prompts.onboarding_prompts import OnboardingPrompts
from kargo_mcp_server.prompts.troubleshooting_prompts import TroubleshootingPrompts
from kargo_mcp_server.prompts.approval_prompts import ApprovalPrompts
from kargo_mcp_server.prompts.rollback_prompts import RollbackPrompts


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize all prompt modules."""
    registry = PromptRegistry()

    registry.register_prompt(PromotionPrompts(service_locator))
    registry.register_prompt(OnboardingPrompts(service_locator))
    registry.register_prompt(TroubleshootingPrompts(service_locator))
    registry.register_prompt(ApprovalPrompts(service_locator))
    registry.register_prompt(RollbackPrompts(service_locator))

    return registry
