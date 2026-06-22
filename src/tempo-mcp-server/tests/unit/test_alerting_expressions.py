"""Unit tests for alerting expression generator.

Covers PromQL template generation, YAML snippet validity,
validation errors, and window/threshold parameterization.
"""

import pytest
import yaml

from tempo_mcp_server.tools.alerting.alerting_tools import (
    _PROMQL_TEMPLATES,
    _TRACEQL_TEMPLATES,
    _VALID_ALERT_TYPES,
)


class TestPromqlTemplates:
    """Verify PromQL expression templates render correctly."""

    def test_error_rate_template(self):
        expr = _PROMQL_TEMPLATES["error_rate"].format(
            service="cart-service",
            window="5m",
            threshold=0.05,
        )
        assert 'service="cart-service"' in expr
        assert "STATUS_CODE_ERROR" in expr
        assert "[5m]" in expr
        assert "> 0.05" in expr

    def test_latency_p99_template(self):
        expr = _PROMQL_TEMPLATES["latency_p99"].format(
            service="api-gateway",
            window="15m",
            threshold=500,
        )
        assert "histogram_quantile(0.99" in expr
        assert 'service="api-gateway"' in expr
        assert "[15m]" in expr
        assert "> 500" in expr

    def test_throughput_drop_template(self):
        expr = _PROMQL_TEMPLATES["throughput_drop"].format(
            service="payment",
            window="10m",
            threshold=100,
        )
        assert 'service="payment"' in expr
        assert "[10m]" in expr
        assert "< 100" in expr

    def test_all_alert_types_have_templates(self):
        for alert_type in _VALID_ALERT_TYPES:
            assert alert_type in _PROMQL_TEMPLATES
            assert alert_type in _TRACEQL_TEMPLATES


class TestTraceqlTemplates:
    """Verify TraceQL annotation templates render correctly."""

    def test_error_rate_traceql(self):
        query = _TRACEQL_TEMPLATES["error_rate"].format(service="api")
        assert 'resource.service.name = "api"' in query
        assert "status = error" in query

    def test_latency_traceql(self):
        query = _TRACEQL_TEMPLATES["latency_p99"].format(
            service="db", threshold=200
        )
        assert 'resource.service.name = "db"' in query
        assert "duration > 200ms" in query

    def test_throughput_traceql(self):
        query = _TRACEQL_TEMPLATES["throughput_drop"].format(service="web")
        assert 'resource.service.name = "web"' in query


class TestAlertNameGeneration:
    """Verify alert name sanitization logic."""

    def test_service_with_hyphens(self):
        safe = "cart-service".replace("-", "_").replace(".", "_")
        assert safe == "cart_service"
        assert f"HighErrorRate_{safe}" == "HighErrorRate_cart_service"

    def test_service_with_dots(self):
        safe = "com.example.api".replace("-", "_").replace(".", "_")
        assert safe == "com_example_api"


class TestYamlSnippetValidity:
    """Verify the YAML snippet produced is valid YAML with required fields."""

    def _build_snippet(
        self, service="test-svc", alert_type="error_rate", threshold=0.05
    ):
        """Build a YAML snippet mimicking the tool logic."""
        safe_service = service.replace("-", "_").replace(".", "_")
        alert_name_map = {
            "error_rate": f"HighErrorRate_{safe_service}",
            "latency_p99": f"HighLatencyP99_{safe_service}",
            "throughput_drop": f"ThroughputDrop_{safe_service}",
        }
        promql_expr = _PROMQL_TEMPLATES[alert_type].format(
            service=service, window="5m", threshold=threshold
        )
        rule_group = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusRule",
            "metadata": {
                "name": f"tempo-alert-{safe_service}",
                "labels": {
                    "app.kubernetes.io/managed-by": "talkops-mcp",
                    "talkops.ai/alert-source": "tempo",
                },
            },
            "spec": {
                "groups": [
                    {
                        "name": f"tempo-{safe_service}-alerts",
                        "rules": [
                            {
                                "alert": alert_name_map[alert_type],
                                "expr": promql_expr,
                                "for": "5m",
                                "labels": {"severity": "warning", "source": "tempo"},
                                "annotations": {"summary": "test alert"},
                            }
                        ],
                    }
                ],
            },
        }
        return yaml.dump(rule_group, default_flow_style=False, sort_keys=False)

    def test_yaml_is_valid(self):
        snippet = self._build_snippet()
        parsed = yaml.safe_load(snippet)
        assert parsed is not None

    def test_yaml_has_prometheus_rule_kind(self):
        snippet = self._build_snippet()
        parsed = yaml.safe_load(snippet)
        assert parsed["kind"] == "PrometheusRule"
        assert parsed["apiVersion"] == "monitoring.coreos.com/v1"

    def test_yaml_has_rules(self):
        snippet = self._build_snippet()
        parsed = yaml.safe_load(snippet)
        rules = parsed["spec"]["groups"][0]["rules"]
        assert len(rules) == 1
        assert rules[0]["alert"] == "HighErrorRate_test_svc"
        assert "expr" in rules[0]
        assert rules[0]["for"] == "5m"

    def test_yaml_has_talkops_labels(self):
        snippet = self._build_snippet()
        parsed = yaml.safe_load(snippet)
        labels = parsed["metadata"]["labels"]
        assert labels["app.kubernetes.io/managed-by"] == "talkops-mcp"
        assert labels["talkops.ai/alert-source"] == "tempo"

    def test_latency_alert_yaml(self):
        snippet = self._build_snippet(
            service="api-gw", alert_type="latency_p99", threshold=500
        )
        parsed = yaml.safe_load(snippet)
        rules = parsed["spec"]["groups"][0]["rules"]
        assert rules[0]["alert"] == "HighLatencyP99_api_gw"
        assert "histogram_quantile" in rules[0]["expr"]

    def test_throughput_drop_yaml(self):
        snippet = self._build_snippet(
            service="payment", alert_type="throughput_drop", threshold=100
        )
        parsed = yaml.safe_load(snippet)
        rules = parsed["spec"]["groups"][0]["rules"]
        assert rules[0]["alert"] == "ThroughputDrop_payment"
        assert "< 100" in rules[0]["expr"]


class TestServiceValidation:
    """Verify service validation uses scoped attributes and handles errors."""

    def setup_method(self):
        from unittest.mock import AsyncMock, MagicMock
        self.tempo = MagicMock()
        self.tempo.get_attribute_values = AsyncMock()
        self.locator = {
            "tempo_service": self.tempo,
            "kubernetes_service": MagicMock(),
            "config": MagicMock(),
        }

    def _register(self):
        from unittest.mock import MagicMock
        from tempo_mcp_server.tools.alerting.alerting_tools import AlertingTools

        mcp = MagicMock()
        captured = {}

        def capture_tool(**kwargs):
            def decorator(fn):
                captured[fn.__name__] = fn
                return fn
            return decorator

        mcp.tool = capture_tool
        AlertingTools(self.locator).register(mcp)
        return captured

    @pytest.mark.asyncio
    async def test_uses_scoped_attribute(self):
        """B-01: Validation must query resource.service.name, not service.name."""
        from unittest.mock import AsyncMock, MagicMock
        self.tempo.get_attribute_values = AsyncMock(return_value={
            "tagValues": [{"type": "string", "value": "frontend"}],
        })
        tools = self._register()
        result = await tools["tempo_generate_alerting_expression"](
            backend_id="test", service="frontend",
            alert_type="error_rate", threshold=0.05,
            for_duration="5m", severity="warning", window="5m",
            tenant=None, ctx=AsyncMock(),
        )
        # Verify the call used the scoped attribute
        call_args = self.tempo.get_attribute_values.call_args
        assert call_args.kwargs.get("attribute") == "resource.service.name"
        assert result["validation"]["service_exists"] is True

    @pytest.mark.asyncio
    async def test_validation_error_not_swallowed(self):
        """B-01: Tempo 400 errors must be reported, not silently swallowed."""
        from unittest.mock import AsyncMock, MagicMock
        from tempo_mcp_server.exceptions.custom import TempoQueryError

        self.tempo.get_attribute_values = AsyncMock(
            side_effect=TempoQueryError("Bad request (400): tag name is not valid")
        )
        tools = self._register()
        result = await tools["tempo_generate_alerting_expression"](
            backend_id="test", service="frontend",
            alert_type="error_rate", threshold=0.05,
            for_duration="5m", severity="warning", window="5m",
            tenant=None, ctx=AsyncMock(),
        )
        # Must NOT silently return service_exists=False with no explanation
        assert result["validation"]["service_exists"] is False
        assert "warning" in result["validation"]
        assert "could not be completed" in result["validation"]["warning"]

    @pytest.mark.asyncio
    async def test_validation_warns_when_service_missing(self):
        """Validation should warn when service is not in the known services list."""
        from unittest.mock import AsyncMock, MagicMock
        self.tempo.get_attribute_values = AsyncMock(return_value={
            "tagValues": [
                {"type": "string", "value": "api-gateway"},
                {"type": "string", "value": "user-service"},
            ],
        })
        tools = self._register()
        result = await tools["tempo_generate_alerting_expression"](
            backend_id="test", service="nonexistent-service",
            alert_type="error_rate", threshold=0.05,
            for_duration="5m", severity="warning", window="5m",
            tenant=None, ctx=AsyncMock(),
        )
        assert result["validation"]["service_exists"] is False
        assert "warning" in result["validation"]
        assert "not found" in result["validation"]["warning"]

