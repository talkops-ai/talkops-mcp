"""Prompts module initialization."""

from typing import Any, Dict

from loki_mcp_server.prompts.registry import PromptRegistry
from loki_mcp_server.prompts.loki_prompts import LokiPrompts


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    """Initialize all prompts and return the registry."""
    registry = PromptRegistry(service_locator)
    registry.register_prompt(LokiPrompts(service_locator))
    return registry
