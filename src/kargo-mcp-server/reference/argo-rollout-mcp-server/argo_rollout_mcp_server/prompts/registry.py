"""Prompt registry for managing all prompts."""

from typing import Dict, Any, List
from argo_rollout_mcp_server.prompts.base import BasePrompt


class PromptRegistry:
    """Registry for managing prompts."""
    
    def __init__(self, service_locator: Dict[str, Any]):
        self.service_locator = service_locator
        self.prompts: List[BasePrompt] = []
    
    def register_prompt(self, prompt: BasePrompt) -> None:
        self.prompts.append(prompt)
    
    def register_all_prompts(self, mcp_instance) -> None:
        for prompt in self.prompts:
            prompt.register(mcp_instance)
