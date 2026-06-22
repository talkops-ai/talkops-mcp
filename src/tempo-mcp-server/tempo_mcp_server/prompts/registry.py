"""Prompt registry for managing all prompts."""

from typing import List
from tempo_mcp_server.prompts.base import BasePrompt


class PromptRegistry:
    """Registry for managing prompts."""

    def __init__(self):
        self.prompts: List[BasePrompt] = []

    def register_prompt(self, prompt: BasePrompt) -> None:
        self.prompts.append(prompt)

    def register_all_prompts(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        for prompt in self.prompts:
            prompt.register(mcp_instance)
