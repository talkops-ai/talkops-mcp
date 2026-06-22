"""Unit tests for request building: URL construction, headers, query params.

Covers §6.2–§6.4 request building, tenant header injection, LLM accept header,
and query parameter assembly.
"""

import pytest
from unittest.mock import AsyncMock

import httpx
import respx

from tempo_mcp_server.config import BackendConfig, ServerConfig, KubernetesConfig
from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.exceptions import TempoTenantError


@pytest.fixture
def svc() -> TempoService:
    """TempoService with both single-tenant and multi-tenant backends."""
    config = ServerConfig(
        backends=[
            BackendConfig(id="single", base_url="http://tempo-single:3200", multi_tenant=False),
            BackendConfig(id="multi", base_url="http://tempo-multi:3200", multi_tenant=True, default_tenant="team-a"),
            BackendConfig(id="no-llm", base_url="http://tempo-no-llm:3200", llm_format_supported=False),
        ],
        kubernetes=KubernetesConfig(enabled=False),
    )
    return TempoService(config)


class TestHeaderBuilding:
    """Verify header construction for various backend configs."""

    def test_no_tenant_header_for_single_tenant(self, svc):
        backend = svc._get_backend("single")
        headers = svc._build_headers(backend)
        assert "X-Scope-OrgID" not in headers

    def test_default_tenant_injected_for_multi(self, svc):
        backend = svc._get_backend("multi")
        headers = svc._build_headers(backend)
        assert headers["X-Scope-OrgID"] == "team-a"

    def test_explicit_tenant_override(self, svc):
        backend = svc._get_backend("multi")
        headers = svc._build_headers(backend, tenant="team-b")
        assert headers["X-Scope-OrgID"] == "team-b"

    def test_missing_tenant_on_multi_raises(self, svc):
        backend = BackendConfig(id="x", multi_tenant=True, base_url="http://x:3200")
        with pytest.raises(TempoTenantError, match="requires tenant"):
            svc._build_headers(backend)

    # §11 #3: test_get_trace_sets_llm_accept_header
    def test_accept_header_llm_format(self, svc):
        backend = svc._get_backend("single")
        headers = svc._build_headers(backend, accept="application/vnd.grafana.llm")
        assert headers["Accept"] == "application/vnd.grafana.llm"

    def test_accept_header_omitted_when_not_supported(self, svc):
        backend = svc._get_backend("no-llm")
        headers = svc._build_headers(backend)
        assert headers.get("Accept") != "application/vnd.grafana.llm"


class TestTenantValidation:
    """Verify tenant ID format constraints (max 150 bytes, restricted charset)."""

    def test_valid_simple_tenant(self, svc):
        svc._validate_tenant("team-alpha")

    def test_valid_cross_tenant_pipe(self, svc):
        svc._validate_tenant("team-a|team-b")

    def test_invalid_chars_raises(self, svc):
        with pytest.raises(TempoTenantError, match="Invalid tenant"):
            svc._validate_tenant("team@evil")

    def test_too_long_raises(self, svc):
        with pytest.raises(TempoTenantError, match="exceeds"):
            svc._validate_tenant("a" * 200)


class TestSearchParamAssembly:
    """Verify query parameter construction for /api/search."""

    # §11 #2: test_traceql_search_builds_correct_params
    @respx.mock
    @pytest.mark.asyncio
    async def test_search_params_assembled_correctly(self, svc):
        route = respx.get("http://tempo-single:3200/api/search").mock(
            return_value=httpx.Response(200, json={"traces": []})
        )
        await svc.traceql_search(
            "single", q='{ status = error }', start=100.0, end=200.0, limit=10, spss=3,
        )
        assert route.called
        request = route.calls[0].request
        params = dict(request.url.params)
        assert params["q"] == "{ status = error }"
        assert params["limit"] == "10"
        assert params["spss"] == "3"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_without_optional_params(self, svc):
        route = respx.get("http://tempo-single:3200/api/search").mock(
            return_value=httpx.Response(200, json={"traces": []})
        )
        await svc.traceql_search("single")
        assert route.called


class TestTraceEndpointURL:
    """Verify /api/v2/traces/<traceID> URL construction."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_trace_url_includes_trace_id(self, svc):
        trace_id = "1234567890abcdef1234567890abcdef"
        route = respx.get(f"http://tempo-single:3200/api/v2/traces/{trace_id}").mock(
            return_value=httpx.Response(200, json={"resourceSpans": []})
        )
        await svc.get_trace("single", trace_id)
        assert route.called


class TestMetricsParamAssembly:
    """Verify metrics query parameter construction."""

    # §11 #6: test_metrics_range_builds_time_window
    @respx.mock
    @pytest.mark.asyncio
    async def test_metrics_range_time_window(self, svc):
        route = respx.get("http://tempo-single:3200/api/metrics/query_range").mock(
            return_value=httpx.Response(200, json={"status": "success", "data": {"result": []}})
        )
        await svc.metrics_query_range("single", q="{ } | rate()", start=1000.0, end=2000.0, step="30s")
        assert route.called
        params = dict(route.calls[0].request.url.params)
        assert "q" in params
        assert "start" in params
        assert "end" in params
