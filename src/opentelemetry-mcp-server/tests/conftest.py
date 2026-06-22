"""Shared test fixtures for the OpenTelemetry MCP server test suite.

Provides mock service locators, sample K8s API responses, and
collector configurations for deterministic testing without K8s access.
"""

import json
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP

from opentelemetry_mcp_server.config import (
    KubernetesConfig,
    ServerConfig,
)
from opentelemetry_mcp_server.services.collector_config_service import (
    CollectorConfigService,
)
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService

# ──────────────────────────────────────────────
# Fixture Loading Helpers
# ──────────────────────────────────────────────


def _load_fixture(name: str) -> Any:
    """Load a JSON fixture from the tests/fixtures/otel directory."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "fixtures", "otel", f"{name}.json"
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────
# Test Assert Helpers
# ──────────────────────────────────────────────


def get_text(result: Any) -> str:
    """Helper to extract text from a CallToolResult."""
    if hasattr(result, "content") and result.content:
        return result.content[0].text
    if isinstance(result, list) and len(result) > 0 and hasattr(result[0], "text"):
        return result[0].text
    return str(result)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def server_config() -> ServerConfig:
    """Provide a test ServerConfig."""
    return ServerConfig(
        name="test-otel-mcp-server",
        version="0.0.1-test",
        kubernetes=KubernetesConfig(enabled=False),
    )


@pytest.fixture
def collector_config_service() -> CollectorConfigService:
    """Provide a real CollectorConfigService (stateless, no mocks needed)."""
    return CollectorConfigService()


@pytest.fixture
def sample_collector_cr() -> Dict[str, Any]:
    """Provide a sample collector CRD dict."""
    return _load_fixture("collector_cr")


@pytest.fixture
def sample_instrumentation_cr() -> Dict[str, Any]:
    """Provide a sample instrumentation CRD dict."""
    return _load_fixture("instrumentation_cr")


@pytest.fixture
def mock_kubernetes_service() -> KubernetesService:
    """Provide a mocked KubernetesService."""
    service = MagicMock(spec=KubernetesService)
    service.is_available = True

    # Default mock responses
    service.list_otel_collectors = AsyncMock(
        return_value={"items": [_load_fixture("collector_cr")]}
    )
    service.get_otel_collector = AsyncMock(
        return_value=_load_fixture("collector_cr")
    )
    service.list_instrumentations = AsyncMock(
        return_value={"items": [_load_fixture("instrumentation_cr")]}
    )
    service.get_instrumentation = AsyncMock(
        return_value=_load_fixture("instrumentation_cr")
    )
    service.list_deployments = AsyncMock(return_value=_load_fixture("deployments_response"))
    service.list_pods = AsyncMock(return_value=_load_fixture("pods_ebpf_response"))
    service.health_check = AsyncMock(return_value=_load_fixture("k8s_health_response"))

    return service


@pytest.fixture
def service_locator(
    mock_kubernetes_service: KubernetesService,
    collector_config_service: CollectorConfigService,
    server_config: ServerConfig,
) -> Dict[str, Any]:
    """Provide a complete service locator with mocked services."""
    return {
        "kubernetes_service": mock_kubernetes_service,
        "collector_config_service": collector_config_service,
        "config": server_config,
    }


@pytest.fixture
def bootstrapped_mcp(
    mock_kubernetes_service: KubernetesService, server_config: ServerConfig
) -> FastMCP:
    """Provide a fully bootstrapped MCP server with mocked services."""
    os.environ["K8S_ENABLED"] = "false"

    from opentelemetry_mcp_server.prompts import initialize_prompts
    from opentelemetry_mcp_server.resources import initialize_resources
    from opentelemetry_mcp_server.server.core import create_mcp_server
    from opentelemetry_mcp_server.tools import initialize_tools

    mcp = create_mcp_server(server_config)

    locator = {
        "kubernetes_service": mock_kubernetes_service,
        "collector_config_service": CollectorConfigService(),
        "config": server_config,
    }

    tool_registry = initialize_tools(locator)
    tool_registry.register_all_tools(mcp)

    resource_registry = initialize_resources(locator)
    resource_registry.register_all_resources(mcp)

    prompt_registry = initialize_prompts(locator)
    prompt_registry.register_all_prompts(mcp)

    return mcp
