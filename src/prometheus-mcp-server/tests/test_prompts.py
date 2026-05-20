"""Tests for MCP prompt modules."""

from unittest.mock import MagicMock

import pytest

from prometheus_mcp_server.prompts.onboarding_prompts import OnboardingPrompts
from prometheus_mcp_server.prompts.troubleshooting_prompts import TroubleshootingPrompts
from prometheus_mcp_server.prompts.query_prompts import QueryPrompts


def _register_prompts(prompt_cls):
    """Register prompts on a mock MCP instance and capture them."""
    sl = {"prometheus_service": MagicMock(), "config": MagicMock()}
    prompt = prompt_cls(sl)
    mcp = MagicMock()
    registered = {}

    def capture_prompt(name, description=""):
        def decorator(fn):
            registered[name] = fn
            return fn
        return decorator

    mcp.prompt = capture_prompt
    prompt.register(mcp)
    return registered


class TestOnboardingPrompts:
    def setup_method(self):
        self.registered = _register_prompts(OnboardingPrompts)

    def test_k8s_app_onboarding_prompt_registered(self):
        assert "prom-k8s-app-onboarding-guided" in self.registered

    def test_k8s_app_onboarding_returns_messages(self):
        messages = self.registered["prom-k8s-app-onboarding-guided"](
            backend_id="test", language="python"
        )
        assert len(messages) == 1
        assert "prom://system/backends" in messages[0].content.text
        assert "prom_recommend_instrumentation" in messages[0].content.text

    def test_k8s_exporter_onboarding_prompt_registered(self):
        assert "prom-k8s-exporter-onboarding-guided" in self.registered

    def test_k8s_exporter_onboarding_returns_messages(self):
        messages = self.registered["prom-k8s-exporter-onboarding-guided"](
            backend_id="test", workload_type="postgres"
        )
        assert len(messages) == 1
        assert "prom_install_exporter" in messages[0].content.text

    def test_vm_legacy_onboarding_prompt_registered(self):
        assert "prom-vm-legacy-onboarding-guided" in self.registered

    def test_vm_legacy_onboarding_returns_messages(self):
        messages = self.registered["prom-vm-legacy-onboarding-guided"](
            backend_id="test", workload_type="custom_app", language="python"
        )
        assert len(messages) == 1
        text = messages[0].content.text
        assert "VM/Legacy" in text
        assert "file_sd" in text
        assert "manage_file_sd" in text


class TestTroubleshootingPrompts:
    def setup_method(self):
        self.registered = _register_prompts(TroubleshootingPrompts)

    def test_troubleshoot_prompt_registered(self):
        assert "prom-troubleshoot-guided" in self.registered

    def test_troubleshoot_returns_messages(self):
        messages = self.registered["prom-troubleshoot-guided"](
            backend_id="test", job="my-app"
        )
        assert len(messages) == 1
        text = messages[0].content.text
        assert "failed_targets" in text
        assert "prom://tsdb/cardinality" in text


class TestQueryPrompts:
    def setup_method(self):
        self.registered = _register_prompts(QueryPrompts)

    def test_query_prompt_registered(self):
        assert "prom-query-guided" in self.registered

    def test_query_returns_messages(self):
        messages = self.registered["prom-query-guided"](
            backend_id="test", metric_name="http_requests_total"
        )
        assert len(messages) == 1
        text = messages[0].content.text
        assert "rate(" in text
        assert "prom_query_instant" in text


class TestRulePrompts:
    def setup_method(self):
        from prometheus_mcp_server.prompts.rule_prompts import RulePrompts
        self.registered = _register_prompts(RulePrompts)

    def test_rule_prompt_registered(self):
        assert "prom-rule-management-guided" in self.registered

    def test_rule_returns_messages(self):
        messages = self.registered["prom-rule-management-guided"](
            backend_id="test"
        )
        assert len(messages) == 1
        text = messages[0].content.text
        assert "prom_draft_alert_rule" in text
        assert "prom_simulate_firing_historical" in text
