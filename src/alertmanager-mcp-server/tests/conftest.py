"""Shared test fixtures for Alertmanager MCP server tests."""
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from alertmanager_mcp_server.config import BackendConfig, LoggingConfig, ServerConfig
from alertmanager_mcp_server.services import AlertmanagerService


@pytest.fixture
def test_backend_config() -> BackendConfig:
    return BackendConfig(
        id="test-am", base_url="http://localhost:9093",
        display_name="Test Alertmanager", labels={"env": "test"},
        verify_ssl=False, is_default=True,
    )


@pytest.fixture
def test_server_config(test_backend_config: BackendConfig) -> ServerConfig:
    return ServerConfig(
        name="test-alertmanager-mcp", version="0.1.0", transport="stdio",
        backends=[test_backend_config], logging=LoggingConfig(level="DEBUG"),
    )


@pytest.fixture
def alertmanager_service(test_server_config: ServerConfig) -> AlertmanagerService:
    return AlertmanagerService(test_server_config)


@pytest.fixture
def service_locator(alertmanager_service: AlertmanagerService, test_server_config: ServerConfig) -> Dict[str, Any]:
    return {"alertmanager_service": alertmanager_service, "config": test_server_config}


@pytest.fixture
def mock_context() -> MagicMock:
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


# Mock Alertmanager API v2 responses
MOCK_STATUS_RESPONSE = {
    "cluster": {"name": "test", "status": "ready", "peers": []},
    "versionInfo": {"version": "0.27.0", "revision": "abc123", "branch": "HEAD"},
    "config": {"original": "route:\n  receiver: default"},
    "uptime": "2024-01-01T00:00:00Z",
}

MOCK_ALERTS_RESPONSE = [
    {
        "fingerprint": "abc123",
        "labels": {"alertname": "HighCPU", "service": "api", "env": "prod", "severity": "warning"},
        "annotations": {"summary": "CPU usage > 90%", "description": "API service CPU is high"},
        "startsAt": "2024-06-01T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "http://prometheus:9090/graph?g0.expr=...",
        "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
    },
    {
        "fingerprint": "def456",
        "labels": {"alertname": "DiskFull", "service": "db", "env": "prod", "severity": "critical"},
        "annotations": {"summary": "Disk usage > 95%"},
        "startsAt": "2024-06-01T09:00:00Z",
        "status": {"state": "active", "silencedBy": [], "inhibitedBy": []},
    },
]

MOCK_ALERT_GROUPS_RESPONSE = [
    {
        "labels": {"alertname": "HighCPU"},
        "alerts": [MOCK_ALERTS_RESPONSE[0]],
    },
    {
        "labels": {"alertname": "DiskFull"},
        "alerts": [MOCK_ALERTS_RESPONSE[1]],
    },
]

MOCK_SILENCES_RESPONSE = [
    {
        "id": "silence-001",
        "matchers": [{"name": "alertname", "value": "HighCPU", "isRegex": False, "isEqual": True}],
        "startsAt": "2024-06-01T10:00:00Z",
        "endsAt": "2024-06-01T12:00:00Z",
        "createdBy": "admin",
        "comment": "Maintenance window",
        "status": {"state": "active"},
        "updatedAt": "2024-06-01T10:00:00Z",
    },
]

MOCK_RECEIVERS_RESPONSE = [
    {"name": "default"},
    {"name": "slack-sre", "slack_configs": [{"channel": "#sre-alerts"}]},
    {"name": "pagerduty-critical", "pagerduty_configs": [{"service_key": "***"}]},
]

MOCK_CREATE_SILENCE_RESPONSE = {"silenceID": "silence-002"}
