"""Prompts module for Alertmanager MCP server."""
from typing import Any, Dict, List
from abc import ABC, abstractmethod


class BasePrompt(ABC):
    def __init__(self, service_locator: Dict[str, Any]):
        self.alertmanager_service = service_locator.get('alertmanager_service')

    @abstractmethod
    def register(self, mcp_instance) -> None:
        pass


class PromptRegistry:
    def __init__(self):
        self.prompts: List[BasePrompt] = []

    def register_prompt(self, prompt: BasePrompt) -> None:
        self.prompts.append(prompt)

    def register_all_prompts(self, mcp_instance) -> None:
        for prompt in self.prompts:
            prompt.register(mcp_instance)


from alertmanager_mcp_server.prompts.triage_prompts import TriagePrompts
from alertmanager_mcp_server.prompts.silence_prompts import SilencePrompts
from alertmanager_mcp_server.prompts.onboarding_prompts import OnboardingPrompts


def initialize_prompts(service_locator: Dict[str, Any]) -> PromptRegistry:
    registry = PromptRegistry()
    registry.register_prompt(TriagePrompts(service_locator))
    registry.register_prompt(SilencePrompts(service_locator))
    registry.register_prompt(OnboardingPrompts(service_locator))
    return registry
