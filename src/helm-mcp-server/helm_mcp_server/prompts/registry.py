"""Prompt registry for managing all prompts."""

from typing import List
from helm_mcp_server.prompts.base import BasePrompt


class PromptRegistry:
    """Registry for managing prompts.
    
    Encapsulates prompt registration and lifecycle.
    """
    
    def __init__(self):
        """Initialize registry."""
        self.prompts: List[BasePrompt] = []
    
    def register_prompt(self, prompt: BasePrompt) -> None:
        """Register a prompt.
        
        Args:
            prompt: Prompt instance
        """
        self.prompts.append(prompt)
    
    def register_all_prompts(self, mcp_instance) -> None:
        """Register all prompts with FastMCP instance.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        for prompt in self.prompts:
            prompt.register(mcp_instance)

