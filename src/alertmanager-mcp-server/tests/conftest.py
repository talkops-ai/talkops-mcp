"""Shared test fixtures for Alertmanager MCP server v0.2.0 test suite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from alertmanager_mcp_server.config import (
    BackendConfig,
    LoggingConfig,
    ServerConfig,
)
from alertmanager_mcp_server.services import AlertmanagerService
from alertmanager_mcp_server.utils.audit import clear_audit_log


@pytest.fixture(autouse=True)
def _reset_audit_log() -> None:
    clear_audit_log()


@pytest.fixture
def test_backend_config() -> BackendConfig:
    return BackendConfig(
        id="test-am",
        base_url="http://localhost:9093",
        display_name="Test Alertmanager",
        labels={"env": "test"},
        verify_ssl=False,
        is_default=True,
    )


@pytest.fixture
def test_server_config(test_backend_config: BackendConfig) -> ServerConfig:
    return ServerConfig(
        name="test-alertmanager-mcp",
        version="0.2.0",
        transport="stdio",
        allow_write=True,
        toolsets=["all"],
        backends=[test_backend_config],
        logging=LoggingConfig(level="DEBUG"),
    )


@pytest.fixture
def readonly_server_config(test_backend_config: BackendConfig) -> ServerConfig:
    return ServerConfig(
        name="test-alertmanager-mcp-ro",
        version="0.2.0",
        transport="stdio",
        allow_write=False,
        toolsets=["all"],
        backends=[test_backend_config],
        logging=LoggingConfig(level="DEBUG"),
    )


@pytest.fixture
def alertmanager_service(
    test_server_config: ServerConfig,
) -> AlertmanagerService:
    return AlertmanagerService(test_server_config)


@pytest.fixture
def service_locator(
    alertmanager_service: AlertmanagerService,
    test_server_config: ServerConfig,
) -> Dict[str, Any]:
    return {
        "alertmanager_service": alertmanager_service,
        "config": test_server_config,
    }


@pytest.fixture
def mock_context() -> MagicMock:
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


SAMPLE_COMPLEX_CONFIG_YAML = """
global:
  resolve_timeout: 5m
  smtp_auth_password: "global-smtp-secret-password"

time_intervals:
  - name: offhours-weekend
    time_intervals:
      - weekdays: ["saturday", "sunday"]
        location: "UTC"
  - name: business-hours
    time_intervals:
      - weekdays: ["monday:friday"]
        times:
          - start_time: "09:00"
            end_time: "17:00"
        location: "UTC"

route:
  receiver: default-slack
  group_by: ["alertname", "cluster", "service"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - alertname="Watchdog"
      receiver: deadmanssnitch
      group_wait: 0s
      group_interval: 1m
      repeat_interval: 1m
      continue: false
    - matchers:
        - '{env="prod", service=~"checkout|payments"}'
      receiver: payments-slack
      group_by: ["alertname", "service", "instance"]
      continue: false
      routes:
        - match:
            severity: critical
          receiver: payments-pagerduty
          repeat_interval: 30m
          continue: true
        - match_re:
            severity: "critical|warning"
          receiver: payments-audit-webhook
          mute_time_intervals:
            - offhours-weekend
    - match:
        team: platform
      receiver: platform-slack

inhibit_rules:
  - source_matchers:
      - severity="critical"
      - alertname="NodeDown"
    target_matchers:
      - severity="warning"
    equal: ["env", "cluster", "service"]

receivers:
  - name: default-slack
    slack_configs:
      - channel: "#alerts-default"
        api_url: "https://hooks.slack.com/services/T000/B000/SECRET_DEFAULT"
  - name: deadmanssnitch
    webhook_configs:
      - url: "https://nosnch.in/c2VjcmV0"
  - name: payments-slack
    slack_configs:
      - channel: "#payments-alerts"
        api_url: "https://hooks.slack.com/services/T000/B000/SECRET_PAY"
  - name: payments-pagerduty
    pagerduty_configs:
      - routing_key: "pd-secret-routing-key-123"
        http_config:
          authorization:
            type: Bearer
            credentials: "super-secret-bearer-token"
          headers:
            X-Custom-Auth: "custom-header-secret"
  - name: payments-audit-webhook
    webhook_configs:
      - url: "https://user:pass123@webhook.internal.example.com/hook"
  - name: platform-slack
    slack_configs:
      - channel: "#platform-alerts"
"""

SAMPLE_METRICS_TEXT = """
# HELP alertmanager_config_last_reload_successful Whether the last configuration reload attempt was successful.
# TYPE alertmanager_config_last_reload_successful gauge
alertmanager_config_last_reload_successful 1
alertmanager_config_last_reload_success_timestamp_seconds 1743242400
# HELP alertmanager_cluster_members Number indicating current number of members in cluster.
# TYPE alertmanager_cluster_members gauge
alertmanager_cluster_members 3
alertmanager_cluster_failed_peers 0
# HELP alertmanager_notifications_total The total number of attempted notifications.
# TYPE alertmanager_notifications_total counter
alertmanager_notifications_total{integration="slack"} 120
alertmanager_notifications_total{integration="pagerduty"} 45
alertmanager_notifications_total{integration="webhook"} 10
# HELP alertmanager_notifications_failed_total The total number of failed notifications.
# TYPE alertmanager_notifications_failed_total counter
alertmanager_notifications_failed_total{integration="slack",reason="client_error"} 0
alertmanager_notifications_failed_total{integration="pagerduty",reason="server_error"} 3
alertmanager_notifications_failed_total{integration="webhook",reason="timeout"} 0
alertmanager_alerts_invalid_total 0
"""

MOCK_STATUS_RESPONSE = {
    "cluster": {"name": "test", "status": "ready", "peers": [{"name": "peer-1", "address": "10.0.0.1:9094"}]},
    "versionInfo": {"version": "0.27.0", "revision": "abc123", "branch": "HEAD", "buildDate": "2024-05-01"},
    "config": {"original": SAMPLE_COMPLEX_CONFIG_YAML},
    "uptime": "2026-03-01T00:00:00Z",
}

_NOW = datetime.now(timezone.utc)
_START_2H_AGO = (_NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
_START_48H_AGO = (_NOW - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
_END_1H_AHEAD = (_NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

MOCK_ALERTS_RESPONSE = [
    {
        "fingerprint": "fp-watchdog",
        "labels": {"alertname": "Watchdog", "severity": "none"},
        "annotations": {"summary": "Pipeline heartbeat", "runbook_url": "https://runbooks.example.com/watchdog"},
        "startsAt": _START_48H_AGO,
        "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
        "receivers": [{"name": "deadmanssnitch"}],
    },
    {
        "fingerprint": "abc123",
        "labels": {
            "alertname": "HighLatency",
            "service": "checkout",
            "env": "prod",
            "cluster": "us-east-1",
            "team": "payments",
            "severity": "critical",
            "instance": "checkout-01:8080",
        },
        "annotations": {
            "summary": "Checkout p99 latency > 2s",
            "runbook_url": "https://runbooks.example.com/checkout-latency",
        },
        "startsAt": _START_2H_AGO,
        "generatorURL": "http://prometheus:9090/graph",
        "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
        "receivers": [{"name": "payments-pagerduty"}, {"name": "payments-audit-webhook"}],
    },
    {
        "fingerprint": "def456",
        "labels": {
            "alertname": "UnroutedDiskWarning",
            "service": "legacy-batch",
            "env": "prod",
            "cluster": "us-east-1",
            "severity": "page",
        },
        "annotations": {},
        "startsAt": _START_48H_AGO,
        "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
        "receivers": [{"name": "default-slack"}],
    },
]

MOCK_ALERT_GROUPS_RESPONSE = [
    {
        "labels": {"alertname": "HighLatency", "service": "checkout"},
        "receiver": {"name": "payments-pagerduty"},
        "alerts": [MOCK_ALERTS_RESPONSE[1]],
    },
    {
        "labels": {"alertname": "UnroutedDiskWarning", "service": "legacy-batch"},
        "receiver": {"name": "default-slack"},
        "alerts": [MOCK_ALERTS_RESPONSE[2]],
    },
]

MOCK_SILENCES_RESPONSE = [
    {
        "id": "silence-001",
        "matchers": [
            {"name": "alertname", "value": "HighLatency", "isRegex": False, "isEqual": True},
            {"name": "service", "value": "checkout", "isRegex": False, "isEqual": True},
        ],
        "startsAt": _START_2H_AGO,
        "endsAt": _END_1H_AHEAD,
        "createdBy": "sre@example.com",
        "comment": "CHG-101: Planned maintenance window",
        "status": {"state": "active"},
        "updatedAt": _START_2H_AGO,
    },
]

MOCK_RECEIVERS_RESPONSE = [
    {"name": "default-slack"},
    {"name": "deadmanssnitch"},
    {"name": "payments-slack"},
    {"name": "payments-pagerduty"},
    {"name": "payments-audit-webhook"},
    {"name": "platform-slack"},
]

MOCK_CREATE_SILENCE_RESPONSE = {"silenceID": "silence-002"}
