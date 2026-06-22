"""Prompts module initialization."""

from typing import Any, Dict
from tempo_mcp_server.prompts.registry import PromptRegistry
from tempo_mcp_server.prompts.troubleshooting_prompts import TroubleshootingPrompts
from tempo_mcp_server.prompts.query_prompts import QueryPrompts


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize all prompt modules."""
    registry = PromptRegistry()

    registry.register_prompt(TroubleshootingPrompts(service_locator))
    registry.register_prompt(QueryPrompts(service_locator))

    return registry
