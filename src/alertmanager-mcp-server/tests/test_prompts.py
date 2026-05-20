from typing import Any
"""Tests for MCP prompt registration and content."""
from unittest.mock import MagicMock

import pytest

from alertmanager_mcp_server.prompts import initialize_prompts
from alertmanager_mcp_server.prompts.triage_prompts import TriagePrompts
from alertmanager_mcp_server.prompts.silence_prompts import SilencePrompts
from alertmanager_mcp_server.prompts.onboarding_prompts import OnboardingPrompts


class TestPromptRegistration:
    """Test that all prompts register correctly."""

    def test_initialize_prompts_creates_registry(self, service_locator):
        registry = initialize_prompts(service_locator)
        assert len(registry.prompts) == 3

    def test_registry_registers_all_prompts(self, service_locator):
        registry = initialize_prompts(service_locator)
        mcp = MagicMock()
        mcp.prompt = MagicMock(return_value=lambda f: f)
        registry.register_all_prompts(mcp)
        assert mcp.prompt.call_count == 3


class TestTriagePrompts:
    """Test triage prompt content."""

    def test_triage_prompt_registers(self, service_locator):
        prompt = TriagePrompts(service_locator)
        mcp = MagicMock()
        captured_fn: Any = None

        def capture_prompt(**kwargs):
            def decorator(f):
                nonlocal captured_fn
                captured_fn = f
                return f
            return decorator
        mcp.prompt = capture_prompt
        prompt.register(mcp)
        assert captured_fn is not None

    def test_triage_prompt_content(self, service_locator):
        prompt = TriagePrompts(service_locator)
        mcp = MagicMock()
        captured_fn: Any = None

        def capture_prompt(**kwargs):
            def decorator(f):
                nonlocal captured_fn
                captured_fn = f
                return f
            return decorator
        mcp.prompt = capture_prompt
        prompt.register(mcp)
        assert captured_fn is not None
        result = captured_fn(backend_id="test-am", service="checkout", env="prod")
        assert len(result) == 1
        assert result[0].role == "user"
        text = result[0].content.text
        assert "am_alert_mgmt" in text
        assert "test-am" in text
        assert "checkout" in text


class TestSilencePrompts:
    """Test silence prompt content."""

    def test_silence_prompt_registers(self, service_locator):
        prompt = SilencePrompts(service_locator)
        mcp = MagicMock()
        captured_fn: Any = None

        def capture_prompt(**kwargs):
            def decorator(f):
                nonlocal captured_fn
                captured_fn = f
                return f
            return decorator
        mcp.prompt = capture_prompt
        prompt.register(mcp)
        assert captured_fn is not None

    def test_silence_prompt_content(self, service_locator):
        prompt = SilencePrompts(service_locator)
        mcp = MagicMock()
        captured_fn: Any = None

        def capture_prompt(**kwargs):
            def decorator(f):
                nonlocal captured_fn
                captured_fn = f
                return f
            return decorator
        mcp.prompt = capture_prompt
        prompt.register(mcp)
        assert captured_fn is not None
        result = captured_fn(backend_id="test-am", service="api", env="staging", duration=120)
        assert len(result) == 1
        text = result[0].content.text
        assert "am_helper_mgmt" in text
        assert "preview_silence" in text
        assert "am_silence_mgmt" in text
        assert "create" in text


class TestOnboardingPrompts:
    """Test onboarding prompt content."""

    def test_onboarding_prompt_registers(self, service_locator):
        prompt = OnboardingPrompts(service_locator)
        mcp = MagicMock()
        captured_fn: Any = None

        def capture_prompt(**kwargs):
            def decorator(f):
                nonlocal captured_fn
                captured_fn = f
                return f
            return decorator
        mcp.prompt = capture_prompt
        prompt.register(mcp)
        assert captured_fn is not None

    def test_onboarding_prompt_content(self, service_locator):
        prompt = OnboardingPrompts(service_locator)
        mcp = MagicMock()
        captured_fn: Any = None

        def capture_prompt(**kwargs):
            def decorator(f):
                nonlocal captured_fn
                captured_fn = f
                return f
            return decorator
        mcp.prompt = capture_prompt
        prompt.register(mcp)
        assert captured_fn is not None
        result = captured_fn(backend_id="test-am", team="sre", receiver="slack-sre")
        assert len(result) == 1
        text = result[0].content.text
        assert "simulate_routing" in text
        assert "push_test" in text
        assert "am://system/receivers" in text
