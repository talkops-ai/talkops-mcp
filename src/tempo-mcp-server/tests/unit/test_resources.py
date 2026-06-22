"""Unit tests for resource content rendering.

Covers §3 (resource content rendering): static docs and policy
resources should produce deterministic, well-formed output.
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock

from tempo_mcp_server.resources.reference_resources import ReferenceResources
from tempo_mcp_server.resources.runbook_resources import RunbookResources
from tempo_mcp_server.resources.examples_resources import ExamplesResources
from tempo_mcp_server.resources.backend_resources import BackendResources
from tempo_mcp_server.resources.deployment_resources import DeploymentResources
from tempo_mcp_server.config import BackendConfig, QueryPolicyConfig, ServerConfig, KubernetesConfig


def _make_service_locator(config=None, tempo_svc=None):
    return {
        "tempo_service": tempo_svc or MagicMock(),
        "config": config or MagicMock(),
    }


def _register_resources(resource_cls, service_locator):
    resource = resource_cls(service_locator)
    mcp = MagicMock()
    registered = {}
    def capture_resource(uri, **kwargs):
        def decorator(fn):
            registered[uri] = fn
            return fn
        return decorator
    mcp.resource = capture_resource
    resource.register(mcp)
    return registered


class TestReferenceResources:
    """Static reference resources produce well-formed markdown."""

    def setup_method(self):
        config = ServerConfig(
            query_policy=QueryPolicyConfig(default_search_limit=20),
            kubernetes=KubernetesConfig(enabled=False),
        )
        sl = _make_service_locator(config=config)
        self.registered = _register_resources(ReferenceResources, sl)

    @pytest.mark.asyncio
    async def test_traceql_reference_contains_selectors(self):
        content = await self.registered["tempo://reference/traceql"]()
        assert "Selectors" in content
        assert "Intrinsics" in content
        assert "duration" in content
        assert "status" in content

    @pytest.mark.asyncio
    async def test_traceql_metrics_reference(self):
        content = await self.registered["tempo://reference/traceql-metrics"]()
        assert "rate()" in content
        assert "count_over_time()" in content
        assert "quantile_over_time" in content

    @pytest.mark.asyncio
    async def test_k8s_attributes_reference(self):
        content = await self.registered["tempo://reference/k8s-attributes"]()
        assert "k8s.namespace.name" in content
        assert "service.name" in content

    @pytest.mark.asyncio
    async def test_query_policies_reflects_config(self):
        content = await self.registered["tempo://reference/query-policies"]()
        assert "20" in content  # default_search_limit
        assert "non-deterministic" in content.lower()


class TestRunbookResources:
    """Runbook resources contain workflow steps."""

    def setup_method(self):
        self.registered = _register_resources(RunbookResources, _make_service_locator())

    @pytest.mark.asyncio
    async def test_latency_spike_runbook(self):
        content = await self.registered["tempo://runbooks/latency-spike"]()
        assert "Detect" in content or "Workflow" in content
        assert "tempo_traceql_metrics_range" in content or "quantile_over_time" in content

    @pytest.mark.asyncio
    async def test_error_burst_runbook(self):
        content = await self.registered["tempo://runbooks/error-burst"]()
        assert "Error" in content or "error" in content
        assert "tempo_traceql_search" in content

    @pytest.mark.asyncio
    async def test_no_traces_runbook(self):
        content = await self.registered["tempo://runbooks/no-traces-found"]()
        assert "Diagnostic" in content or "Verify" in content


class TestExamplesResources:
    """Common queries resource contains working TraceQL examples."""

    def setup_method(self):
        self.registered = _register_resources(ExamplesResources, _make_service_locator())

    @pytest.mark.asyncio
    async def test_common_queries_has_examples(self):
        content = await self.registered["tempo://examples/common-queries"]()
        assert "service.name" in content
        assert "status = error" in content
        assert "duration" in content


class TestDynamicBackendResources:
    """Dynamic backend resources return valid JSON."""

    @pytest.mark.asyncio
    async def test_backends_resource(self):
        tempo = MagicMock()
        tempo.list_backends = AsyncMock(return_value=[
            {"id": "test", "type": "tempo", "health": "ready"},
        ])
        sl = _make_service_locator(tempo_svc=tempo)
        registered = _register_resources(BackendResources, sl)

        result = await registered["tempo://system/backends"]()
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["id"] == "test"
