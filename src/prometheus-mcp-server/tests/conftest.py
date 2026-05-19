"""Shared test fixtures for Prometheus MCP server tests."""

import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from prometheus_mcp_server.config import BackendConfig, KubernetesConfig, LoggingConfig, ServerConfig
from prometheus_mcp_server.services.prometheus_service import PrometheusService
from prometheus_mcp_server.services.kubernetes_service import KubernetesService


@pytest.fixture
def test_backend_config() -> BackendConfig:
    return BackendConfig(
        id="test-backend",
        base_url="http://localhost:9090",
        type="prometheus",
        display_name="Test Prometheus",
        labels={"env": "test"},
        auth_header=None,
        verify_ssl=False,
        timeout=10,
    )


@pytest.fixture
def test_server_config(test_backend_config: BackendConfig) -> ServerConfig:
    return ServerConfig(
        name="test-prometheus-mcp",
        version="0.1.0",
        transport="stdio",
        backends=[test_backend_config],
        kubernetes=KubernetesConfig(enabled=False),
        logging=LoggingConfig(level="DEBUG"),
    )


@pytest.fixture
def prometheus_service(test_server_config: ServerConfig) -> PrometheusService:
    return PrometheusService(test_server_config)


@pytest.fixture
def kubernetes_service() -> KubernetesService:
    config = KubernetesConfig(enabled=False)
    return KubernetesService(config)


@pytest.fixture
def service_locator(
    prometheus_service: PrometheusService,
    kubernetes_service: KubernetesService,
    test_server_config: ServerConfig,
) -> Dict[str, Any]:
    return {
        "prometheus_service": prometheus_service,
        "kubernetes_service": kubernetes_service,
        "config": test_server_config,
    }


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock FastMCP Context."""
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    return ctx


# ----- Mock Prometheus API Responses -----

MOCK_INSTANT_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"__name__": "up", "job": "prometheus", "instance": "localhost:9090"},
                "value": [1700000000, "1"],
            }
        ],
    },
}

MOCK_RANGE_RESPONSE = {
    "status": "success",
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"__name__": "up", "job": "prometheus"},
                "values": [[1700000000 + i * 15, "1"] for i in range(100)],
            }
        ],
    },
}

MOCK_METADATA_RESPONSE = {
    "status": "success",
    "data": {
        "up": [{"type": "gauge", "help": "Target is up", "unit": ""}],
        "http_requests_total": [{"type": "counter", "help": "Total HTTP requests", "unit": ""}],
    },
}

MOCK_LABELS_RESPONSE = {
    "status": "success",
    "data": ["__name__", "job", "instance", "namespace"],
}

MOCK_TARGETS_RESPONSE = {
    "status": "success",
    "data": {
        "activeTargets": [
            {
                "labels": {"job": "prometheus", "instance": "localhost:9090"},
                "health": "up",
                "lastError": "",
            },
            {
                "labels": {"job": "node-exporter", "instance": "node1:9100"},
                "health": "down",
                "lastError": "connection refused",
            },
        ],
        "droppedTargets": [],
    },
}

MOCK_TSDB_STATUS_RESPONSE = {
    "status": "success",
    "data": {
        "headStats": {
            "numSeries": 50000,
            "numLabelPairs": 12000,
            "chunkCount": 150000,
        },
        "seriesCountByMetricName": [
            {"name": "http_requests_total", "value": 5000},
            {"name": "process_cpu_seconds_total", "value": 3000},
        ],
    },
}

MOCK_RUNTIME_INFO_RESPONSE = {
    "status": "success",
    "data": {
        "startTime": "2024-01-01T00:00:00Z",
        "CWD": "/prometheus",
        "reloadConfigSuccess": True,
        "lastConfigTime": "2024-01-01T00:00:00Z",
        "storageRetention": "15d",
    },
}

MOCK_BUILDINFO_RESPONSE = {
    "status": "success",
    "data": {
        "version": "2.48.0",
        "revision": "abc123",
        "branch": "HEAD",
        "goVersion": "go1.21.5",
    },
}
