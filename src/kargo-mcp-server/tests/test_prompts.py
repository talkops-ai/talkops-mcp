"""Tests for MCP prompts registration."""

from typing import Any, Dict

import pytest

from kargo_mcp_server.prompts.promotion_prompts import PromotionPrompts
from kargo_mcp_server.prompts.onboarding_prompts import OnboardingPrompts
from kargo_mcp_server.prompts.troubleshooting_prompts import TroubleshootingPrompts
from kargo_mcp_server.prompts.approval_prompts import ApprovalPrompts
from kargo_mcp_server.prompts.rollback_prompts import RollbackPrompts


def _extract_prompts(prompt_cls, service_locator: Dict[str, Any]) -> Dict[str, Any]:
    """Register prompts on a fake MCP and collect their callables."""
    instance = prompt_cls(service_locator)
    collected: Dict[str, Any] = {}

    class FakeMCP:
        def prompt(self, name: str, **kwargs):
            def decorator(fn):
                collected[name] = fn
                return fn
            return decorator

    instance.register(FakeMCP())
    return collected


class TestPromotionPrompts:
    def test_promotion_guided(self, service_locator):
        prompts = _extract_prompts(PromotionPrompts, service_locator)
        result = prompts["kargo-promotion-guided"](project="demo", target_stage="prod")
        assert len(result) == 1
        assert "Kargo Promotion Workflow" in result[0].content.text


class TestOnboardingPrompts:
    def test_pipeline_onboarding_guided(self, service_locator):
        prompts = _extract_prompts(OnboardingPrompts, service_locator)
        result = prompts["kargo-pipeline-onboarding-guided"](project="demo")
        assert len(result) == 1
        assert "Pipeline Onboarding Guide" in result[0].content.text


class TestTroubleshootingPrompts:
    def test_troubleshoot_guided(self, service_locator):
        prompts = _extract_prompts(TroubleshootingPrompts, service_locator)
        result = prompts["kargo-troubleshoot-guided"](project="demo", stage="prod")
        assert len(result) == 1
        assert "Kargo Troubleshooting Guide" in result[0].content.text


class TestApprovalPrompts:
    def test_approval_guided(self, service_locator):
        prompts = _extract_prompts(ApprovalPrompts, service_locator)
        result = prompts["kargo-approval-guided"](project="demo", stage="prod")
        assert len(result) == 1
        assert "Manual Approval Workflow" in result[0].content.text


class TestRollbackPrompts:
    def test_rollback_guided(self, service_locator):
        prompts = _extract_prompts(RollbackPrompts, service_locator)
        result = prompts["kargo-rollback-guided"](project="demo", stage="prod")
        assert len(result) == 1
        assert "Kargo Rollback Guide" in result[0].content.text
