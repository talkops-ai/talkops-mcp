"""Tests for AlertmanagerService."""
import asyncio
import pytest
import respx
from httpx import Response
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.services import AlertmanagerService, _redact_dict
from tests.conftest import (
    MOCK_ALERTS_RESPONSE, MOCK_ALERT_GROUPS_RESPONSE,
    MOCK_RECEIVERS_RESPONSE, MOCK_SILENCES_RESPONSE, MOCK_STATUS_RESPONSE,
)


class TestServiceBasics:
    def test_list_backends(self, alertmanager_service):
        backends = alertmanager_service.list_backends()
        assert len(backends) == 1
        assert backends[0].id == "test-am"

    def test_unknown_backend_raises(self, alertmanager_service):
        with pytest.raises(ValueError, match="Unknown backend_id"):
            alertmanager_service._get_backend("nonexistent")

    def test_get_default_backend(self, alertmanager_service):
        backend = alertmanager_service._get_default_backend()
        assert backend.id == "test-am"
        assert backend.is_default is True

    def test_list_backends_returns_descriptors(self, alertmanager_service):
        backends = alertmanager_service.list_backends()
        assert backends[0].display_name == "Test Alertmanager"
        assert backends[0].base_url == "http://localhost:9093"


class TestServiceAlerts:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alerts(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        alerts, has_more, _ = await alertmanager_service.list_alerts("test-am")
        assert len(alerts) == 2
        assert alerts[0].labels["alertname"] == "HighCPU"
        assert has_more is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alerts_with_pagination(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        alerts, has_more, next_off = await alertmanager_service.list_alerts("test-am", limit=1, offset=0)
        assert len(alerts) == 1
        assert has_more is True
        assert next_off == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alerts_with_matchers(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        matchers = [AlertMatcher(name="service", value="api", isRegex=False, isEqual=True)]
        alerts, _, _ = await alertmanager_service.list_alerts("test-am", matchers=matchers)
        assert len(alerts) == 2  # server-side mock returns all

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alerts_with_status_filters(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json=MOCK_ALERTS_RESPONSE))
        alerts, _, _ = await alertmanager_service.list_alerts(
            "test-am", active=True, silenced=False, inhibited=False, unprocessed=False,
        )
        assert len(alerts) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alert_groups(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/alerts/groups").mock(return_value=Response(200, json=MOCK_ALERT_GROUPS_RESPONSE))
        groups = await alertmanager_service.list_alert_groups("test-am")
        assert len(groups) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_alert_groups_caps_alerts(self, alertmanager_service):
        """Test that alert groups cap alerts per group."""
        large_group = {
            "labels": {"alertname": "Spam"},
            "alerts": [MOCK_ALERTS_RESPONSE[0].copy() for _ in range(30)],
        }
        respx.get("http://localhost:9093/api/v2/alerts/groups").mock(return_value=Response(200, json=[large_group]))
        groups = await alertmanager_service.list_alert_groups("test-am", max_alerts_per_group=5)
        assert len(groups[0].alerts) == 5

    @respx.mock
    @pytest.mark.asyncio
    async def test_push_alerts(self, alertmanager_service):
        respx.post("http://localhost:9093/api/v2/alerts").mock(return_value=Response(200, json={}))
        result = await alertmanager_service.push_alerts("test-am", [{"labels": {"alertname": "Test"}}])
        assert isinstance(result, dict)


class TestServiceSilences:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_silences(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=MOCK_SILENCES_RESPONSE))
        silences, has_more, _ = await alertmanager_service.list_silences("test-am")
        assert len(silences) == 1
        assert silences[0].id == "silence-001"
        assert has_more is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_silences_pagination(self, alertmanager_service):
        many = [MOCK_SILENCES_RESPONSE[0].copy() for _ in range(5)]
        for i, s in enumerate(many):
            s["id"] = f"s-{i}"
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=many))
        silences, has_more, next_off = await alertmanager_service.list_silences("test-am", limit=2, offset=0)
        assert len(silences) == 2
        assert has_more is True
        assert next_off == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_silences_state_filter(self, alertmanager_service):
        mixed = [
            {**MOCK_SILENCES_RESPONSE[0], "id": "s-active", "status": {"state": "active"}},
            {**MOCK_SILENCES_RESPONSE[0], "id": "s-expired", "status": {"state": "expired"}},
        ]
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=mixed))
        silences, _, _ = await alertmanager_service.list_silences("test-am", state="active")
        assert len(silences) == 1
        assert silences[0].id == "s-active"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_silence(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/silence/silence-001").mock(return_value=Response(200, json=MOCK_SILENCES_RESPONSE[0]))
        silence = await alertmanager_service.get_silence("test-am", "silence-001")
        assert silence.createdBy == "admin"

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_silence(self, alertmanager_service):
        respx.delete("http://localhost:9093/api/v2/silence/silence-001").mock(return_value=Response(200))
        await alertmanager_service.delete_silence("test-am", "silence-001")

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_duplicate_silence_found(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=MOCK_SILENCES_RESPONSE))
        matchers = [AlertMatcher(name="alertname", value="HighCPU", isRegex=False, isEqual=True)]
        dup = await alertmanager_service.find_duplicate_silence("test-am", matchers)
        assert dup is not None
        assert dup.id == "silence-001"

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_duplicate_silence_not_found(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/silences").mock(return_value=Response(200, json=MOCK_SILENCES_RESPONSE))
        matchers = [AlertMatcher(name="alertname", value="DifferentAlert", isRegex=False, isEqual=True)]
        dup = await alertmanager_service.find_duplicate_silence("test-am", matchers)
        assert dup is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_silence(self, alertmanager_service):
        from alertmanager_mcp_server.models.silence import PostableSilence
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        silence = PostableSilence(
            matchers=[AlertMatcher(name="alertname", value="Test", isRegex=False, isEqual=True)],
            startsAt=now, endsAt=now + timedelta(hours=1),
            createdBy="test", comment="test silence",
        )
        respx.post("http://localhost:9093/api/v2/silences").mock(
            return_value=Response(200, json={"id": "new-silence"})
        )
        respx.get("http://localhost:9093/api/v2/silence/new-silence").mock(
            return_value=Response(200, json={**MOCK_SILENCES_RESPONSE[0], "id": "new-silence"})
        )
        created = await alertmanager_service.create_silence("test-am", silence)
        assert created.id == "new-silence"


class TestServiceStatus:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_status(self, alertmanager_service):
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        status = await alertmanager_service.get_status("test-am")
        assert status["versionInfo"]["version"] == "0.27.0"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_health_healthy(self, alertmanager_service):
        respx.get("http://localhost:9093/-/healthy").mock(return_value=Response(200, text="OK"))
        health = await alertmanager_service.check_health("test-am")
        assert health == "healthy"

    @respx.mock
    @pytest.mark.asyncio
    async def test_check_health_unhealthy(self, alertmanager_service):
        respx.get("http://localhost:9093/-/healthy").mock(side_effect=Exception("Connection refused"))
        health = await alertmanager_service.check_health("test-am")
        assert health == "unhealthy"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_receivers(self, alertmanager_service):
        # The new implementation calls both /api/v2/status (for config YAML) and /api/v2/receivers (for names)
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        respx.get("http://localhost:9093/api/v2/receivers").mock(return_value=Response(200, json=MOCK_RECEIVERS_RESPONSE))
        receivers = await alertmanager_service.get_receivers("test-am")
        assert len(receivers) == 3
        names = [r.name for r in receivers]
        assert "slack-sre" in names

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_receivers_type_inference(self, alertmanager_service):
        """Test that receiver types are inferred from the config YAML."""
        config_yaml = """
route:
  receiver: default
receivers:
  - name: slack-test
    slack_configs:
      - channel: '#test'
        api_url: 'https://hooks.slack.com/secret'
  - name: pd-test
    pagerduty_configs:
      - service_key: 'xxx-secret'
  - name: email-test
    email_configs:
      - to: 'test@test.com'
  - name: webhook-test
    webhook_configs:
      - url: 'http://hook.test'
  - name: no-type
"""
        status_with_receivers = {**MOCK_STATUS_RESPONSE, "config": {"original": config_yaml}}
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=status_with_receivers))
        receivers_api = [
            {"name": "slack-test"}, {"name": "pd-test"},
            {"name": "email-test"}, {"name": "webhook-test"}, {"name": "no-type"},
        ]
        respx.get("http://localhost:9093/api/v2/receivers").mock(return_value=Response(200, json=receivers_api))
        receivers = await alertmanager_service.get_receivers("test-am")
        types = {r.name: r.type for r in receivers}
        assert types["slack-test"] == "slack"
        assert types["pd-test"] == "pagerduty"
        assert types["email-test"] == "email"
        assert types["webhook-test"] == "webhook"
        assert types["no-type"] is None
        # Verify redaction: slack api_url should be redacted
        slack_r = next(r for r in receivers if r.name == "slack-test")
        slack_configs = slack_r.details.get("slack_configs", [])
        assert len(slack_configs) > 0
        assert slack_configs[0]["api_url"] == "***REDACTED***"
        assert slack_configs[0]["channel"] == "#test"


class TestServiceRoutingSimulation:
    """Test the routing simulation engine."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_simulate_routing_basic(self, alertmanager_service):
        """Test routing simulation with basic config."""
        status = {
            **MOCK_STATUS_RESPONSE,
            "config": {"original": """
route:
  receiver: default
  routes:
    - matchers:
        - alertname="HighCPU"
      receiver: pagerduty-critical
    - matchers:
        - severity="warning"
      receiver: slack-sre
"""},
        }
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=status))
        result = await alertmanager_service.simulate_routing("test-am", {"alertname": "HighCPU", "severity": "critical"})
        assert "pagerduty-critical" in result.receivers

    @respx.mock
    @pytest.mark.asyncio
    async def test_simulate_routing_fallback(self, alertmanager_service):
        """Test routing falls back to root receiver when nothing matches."""
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        result = await alertmanager_service.simulate_routing("test-am", {"alertname": "Unknown"})
        assert len(result.receivers) >= 1
        assert result.route_path != ""

    @respx.mock
    @pytest.mark.asyncio
    async def test_simulate_routing_with_inhibitions(self, alertmanager_service):
        status = {
            **MOCK_STATUS_RESPONSE,
            "config": {"original": """
route:
  receiver: default
inhibit_rules:
  - source_matchers:
      - severity="critical"
    target_matchers:
      - severity="warning"
    equal:
      - alertname
"""},
        }
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=status))
        result = await alertmanager_service.simulate_routing("test-am", {"alertname": "HighCPU", "severity": "warning"})
        assert len(result.inhibited_by) > 0


class TestServiceConfigSnapshot:
    """Test config snapshot parsing."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_config_snapshot(self, alertmanager_service):
        status = {
            **MOCK_STATUS_RESPONSE,
            "config": {"original": """
route:
  receiver: default
  group_by: [alertname, env]
  routes:
    - matchers:
        - severity="critical"
      receiver: pagerduty
inhibit_rules:
  - source_matchers:
      - severity="critical"
    target_matchers:
      - severity="warning"
    equal: [alertname]
"""},
        }
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=status))
        snapshot = await alertmanager_service.get_config_snapshot("test-am")
        assert len(snapshot.routes) >= 1
        assert len(snapshot.inhibitions) == 1
        assert snapshot.inhibitions[0].equal == ["alertname"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_config_snapshot_empty(self, alertmanager_service):
        """Test config snapshot with minimal config."""
        respx.get("http://localhost:9093/api/v2/status").mock(return_value=Response(200, json=MOCK_STATUS_RESPONSE))
        snapshot = await alertmanager_service.get_config_snapshot("test-am")
        assert isinstance(snapshot.routes, list)
        assert isinstance(snapshot.inhibitions, list)


class TestServiceRetryLogic:
    """Test retry logic on transient failures."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_on_500(self, alertmanager_service):
        """Test that 5xx errors trigger retries."""
        route = respx.get("http://localhost:9093/api/v2/alerts")
        route.side_effect = [
            Response(500, text="Internal Server Error"),
            Response(500, text="Internal Server Error"),
            Response(200, json=MOCK_ALERTS_RESPONSE),
        ]
        alerts, _, _ = await alertmanager_service.list_alerts("test-am")
        assert len(alerts) == 2
        assert route.call_count == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self, alertmanager_service):
        """Test that persistent errors eventually raise."""
        respx.get("http://localhost:9093/api/v2/alerts").mock(return_value=Response(500, text="Server Error"))
        with pytest.raises(RuntimeError, match="Alertmanager API error 500"):
            await alertmanager_service.list_alerts("test-am")

    @respx.mock
    @pytest.mark.asyncio
    async def test_4xx_not_retried(self, alertmanager_service):
        """Test that 4xx errors are NOT retried."""
        route = respx.get("http://localhost:9093/api/v2/alerts")
        route.mock(return_value=Response(404, text="Not Found"))
        with pytest.raises(RuntimeError, match="Alertmanager API error 404"):
            await alertmanager_service.list_alerts("test-am")
        assert route.call_count == 1


class TestServiceGracefulShutdown:
    @pytest.mark.asyncio
    async def test_close(self, alertmanager_service):
        """Test graceful shutdown closes clients."""
        # Trigger client creation
        alertmanager_service._ensure_client("test-am")
        assert "test-am" in alertmanager_service._clients
        await alertmanager_service.close()
        assert len(alertmanager_service._clients) == 0


class TestRedaction:
    def test_redact_dict_basic(self):
        data = {"name": "test", "api_key": "secret123", "channel": "#alerts"}
        result = _redact_dict(data)
        assert result["name"] == "test"
        assert result["api_key"] == "***REDACTED***"
        assert result["channel"] == "#alerts"

    def test_redact_dict_nested(self):
        data = {"configs": [{"token": "abc", "channel": "#test"}]}
        result = _redact_dict(data)
        assert result["configs"][0]["token"] == "***REDACTED***"
        assert result["configs"][0]["channel"] == "#test"

    def test_redact_dict_comprehensive(self):
        """Test all sensitive keys are redacted."""
        sensitive_keys = ["secret", "password", "token", "api_key", "api_url",
                         "routing_key", "service_key", "webhook_url"]
        data = {k: "should-be-redacted" for k in sensitive_keys}
        data["safe_key"] = "should-remain"
        result = _redact_dict(data)
        for k in sensitive_keys:
            assert result[k] == "***REDACTED***", f"Key '{k}' was not redacted"
        assert result["safe_key"] == "should-remain"


class TestServiceMatcherParsing:
    """Test internal matcher string parsing."""

    def test_parse_matcher_string_equal(self):
        m = AlertmanagerService._parse_matcher_string('alertname="HighCPU"')
        assert m is not None
        assert m.name == "alertname"
        assert m.value == "HighCPU"
        assert m.isRegex is False
        assert m.isEqual is True

    def test_parse_matcher_string_not_equal(self):
        m = AlertmanagerService._parse_matcher_string('env!="staging"')
        assert m is not None
        assert m.isEqual is False
        assert m.isRegex is False

    def test_parse_matcher_string_regex(self):
        m = AlertmanagerService._parse_matcher_string('service=~"api.*"')
        assert m is not None
        assert m.isRegex is True
        assert m.isEqual is True

    def test_parse_matcher_string_not_regex(self):
        m = AlertmanagerService._parse_matcher_string('env!~"staging.*"')
        assert m is not None
        assert m.isRegex is True
        assert m.isEqual is False

    def test_parse_matcher_string_invalid(self):
        m = AlertmanagerService._parse_matcher_string("not a matcher")
        assert m is None
