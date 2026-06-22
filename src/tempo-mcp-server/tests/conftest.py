"""Root test fixtures — composable fixtures for both unit and integration tests.

Fixtures defined here (matching §8 of the test spec):
  mock_tempo_http    – respx-based HTTP stubs for Tempo endpoints
  mock_kubernetes_api – mocked K8s API for discovery tests
  mcp_server         – initialized FastMCP instance with tools/resources/prompts
  mcp_client         – in-memory Client bound to mcp_server
  sample_trace_payload    – loaded from fixtures/tempo/trace_response_otlp.json
  sample_metrics_payload  – loaded from fixtures/tempo/metrics_range_response.json
  sample_tag_payload      – loaded from fixtures/tempo/tags_response.json
"""

import json
import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from tempo_mcp_server.config import BackendConfig, KubernetesConfig, QueryPolicyConfig, ServerConfig
from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.services.kubernetes_service import KubernetesService

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "tempo"


def _text(content: Any) -> str:
    """Extract text from an MCP content object (TextContent, ResourceContents, etc.).

    The MCP SDK returns union types for content (TextContent | ImageContent | ...).
    Only TextContent has a `.text` attribute. This helper safely extracts it for tests.
    """
    if hasattr(content, "text"):
        return str(content.text)
    return str(content)


def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# ── Fixture data (loaded once) ──

@pytest.fixture
def sample_trace_payload() -> Dict[str, Any]:
    """OTLP trace payload with 2 spans (1 error, 1 healthy)."""
    return _load_fixture("trace_response_otlp.json")


@pytest.fixture
def sample_metrics_payload() -> Dict[str, Any]:
    """TraceQL metrics range response with 2 series."""
    return _load_fixture("metrics_range_response.json")


@pytest.fixture
def sample_tag_payload() -> Dict[str, Any]:
    """Tags response with resource, span, and intrinsic scopes."""
    return _load_fixture("tags_response.json")


# ── Config fixtures ──

@pytest.fixture
def default_backend() -> BackendConfig:
    return BackendConfig(
        id="test-backend",
        base_url="http://tempo-test:3200",
        type="tempo",
        display_name="Test Tempo",
        deployment_mode="monolithic",
        multi_tenant=False,
    )


@pytest.fixture
def multi_tenant_backend() -> BackendConfig:
    return BackendConfig(
        id="mt-backend",
        base_url="http://tempo-mt:3200",
        type="tempo",
        display_name="Multi-Tenant Tempo",
        deployment_mode="microservices",
        multi_tenant=True,
        default_tenant="team-a",
    )


@pytest.fixture
def query_policy() -> QueryPolicyConfig:
    return QueryPolicyConfig(
        max_lookback="168h",
        default_search_limit=20,
        max_search_limit=100,
        default_spss=3,
        max_spss=10,
        require_time_range=True,
        require_filter_or_query=True,
    )


@pytest.fixture
def server_config(default_backend, query_policy) -> ServerConfig:
    return ServerConfig(
        name="tempo-mcp-server-test",
        version="0.1.0-test",
        transport="stdio",
        backends=[default_backend],
        query_policy=query_policy,
        kubernetes=KubernetesConfig(enabled=False),
    )


@pytest.fixture
def mt_server_config(multi_tenant_backend, query_policy) -> ServerConfig:
    return ServerConfig(
        backends=[multi_tenant_backend],
        query_policy=query_policy,
        kubernetes=KubernetesConfig(enabled=False),
    )


# ── Service fixtures ──

@pytest.fixture
def tempo_service(server_config) -> TempoService:
    return TempoService(server_config)


@pytest.fixture
def mt_tempo_service(mt_server_config) -> TempoService:
    return TempoService(mt_server_config)


@pytest.fixture
def kubernetes_service() -> KubernetesService:
    return KubernetesService(KubernetesConfig(enabled=False))


@pytest.fixture
def service_locator(tempo_service, kubernetes_service, server_config) -> Dict[str, Any]:
    return {
        "tempo_service": tempo_service,
        "kubernetes_service": kubernetes_service,
        "config": server_config,
    }


# ── mock_tempo_http: respx stubs for all Tempo HTTP endpoints ──

@pytest.fixture
def mock_tempo_http():
    """Stub all Tempo HTTP endpoints with canned JSON fixtures."""
    with respx.mock(assert_all_called=False) as mock:
        base = "http://tempo-test:3200"

        mock.get(f"{base}/ready").mock(
            return_value=httpx.Response(200, text="ready")
        )
        mock.get(f"{base}/api/search").mock(
            return_value=httpx.Response(200, json=_load_fixture("search_response.json"))
        )
        mock.get(url__regex=rf"{base}/api/v2/traces/.+").mock(
            return_value=httpx.Response(200, json=_load_fixture("trace_response_otlp.json"))
        )
        mock.get(f"{base}/api/v2/search/tags").mock(
            return_value=httpx.Response(200, json=_load_fixture("tags_response.json"))
        )
        mock.get(url__regex=rf"{base}/api/v2/search/tag/.+/values").mock(
            return_value=httpx.Response(200, json=_load_fixture("tags_values_response.json"))
        )
        mock.get(f"{base}/api/metrics/query_range").mock(
            return_value=httpx.Response(200, json=_load_fixture("metrics_range_response.json"))
        )
        mock.get(f"{base}/api/metrics/query").mock(
            return_value=httpx.Response(200, json=_load_fixture("metrics_instant_response.json"))
        )
        mock.get(f"{base}/api/status/buildinfo").mock(
            return_value=httpx.Response(200, json=_load_fixture("buildinfo.json"))
        )
        mock.get(f"{base}/status/services").mock(
            return_value=httpx.Response(200, json=_load_fixture("status_services.json"))
        )

        yield mock


# ── mock_kubernetes_api ──

@pytest.fixture
def mock_kubernetes_api():
    """Mocked K8s CoreV1Api returning a Tempo service."""
    k8s_mock = MagicMock()
    svc_item = MagicMock()
    svc_item.metadata.name = "tempo-prod"
    svc_item.metadata.namespace = "monitoring"
    svc_item.metadata.labels = {"app.kubernetes.io/name": "tempo", "app.kubernetes.io/component": "query-frontend"}
    port = MagicMock()
    port.name = "http-query"
    port.port = 3200
    svc_item.spec.ports = [port]

    svc_list = MagicMock()
    svc_list.items = [svc_item]
    k8s_mock.list_namespaced_service.return_value = svc_list
    k8s_mock.list_service_for_all_namespaces.return_value = svc_list
    return k8s_mock


# ── mcp_server: fully bootstrapped FastMCP instance ──

@pytest.fixture
def mcp_server(mock_tempo_http):
    """Return a fully initialized FastMCP server instance."""
    env = {
        "TEMPO_BASE_URL": "http://tempo-test:3200",
        "TEMPO_BACKEND_ID": "test-backend",
        "K8S_ENABLED": "false",
    }
    with patch.dict(os.environ, env, clear=False):
        from tempo_mcp_server.server.bootstrap import ServerBootstrap
        mcp, _, _ = ServerBootstrap.initialize()
        return mcp


# ── mcp_client: in-memory FastMCP Client (§7 pattern) ──

@pytest.fixture
async def mcp_client(mcp_server):
    """In-memory MCP client bound to the server instance."""
    from fastmcp import Client
    async with Client(mcp_server) as client:
        yield client


# ── Mock FastMCP context for tool unit tests ──

@pytest.fixture
def mock_context() -> MagicMock:
    ctx = MagicMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    return ctx
