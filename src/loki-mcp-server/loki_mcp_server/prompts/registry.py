"""Prompt registry for managing all Loki MCP prompts."""

from typing import Any, Dict, List

from loki_mcp_server.prompts.base import BasePrompt


class PromptRegistry:
    """Registry for managing prompts."""

    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.prompts: List[BasePrompt] = []

    def register_prompt(self, prompt: BasePrompt) -> None:
        self.prompts.append(prompt)

    def register_all(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        for prompt in self.prompts:
            prompt.register(mcp_instance)
