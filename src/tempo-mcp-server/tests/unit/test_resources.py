"""Unit tests for dynamic/live MCP resources (`tempo://`)."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from tempo_mcp_server.config import BackendConfig, KubernetesConfig, QueryPolicyConfig, ServerConfig
from tempo_mcp_server.resources.backend_resources import BackendResources
from tempo_mcp_server.resources.deployment_resources import DeploymentResources


def _make_service_locator(config=None, tempo_svc=None, k8s_svc=None):
    return {
        "tempo_service": tempo_svc or MagicMock(),
        "kubernetes_service": k8s_svc or MagicMock(),
        "config": config
        or ServerConfig(
            backends=[BackendConfig(id="default", base_url="http://tempo:3200")],
            query_policy=QueryPolicyConfig(default_search_limit=20),
            kubernetes=KubernetesConfig(enabled=False),
        ),
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


class TestBackendResources:
    """Verify live backend, capability, schema, overrides, and trace resources."""

    @pytest.mark.asyncio
    async def test_capabilities_resource(self):
        tempo = MagicMock()
        tempo.get_safe_status_config = AsyncMock(
            return_value={"metrics_generator_processors": ["local-blocks"]}
        )
        tempo.get_build_info = AsyncMock(return_value={"version": "2.9.0"})
        tempo.detect_tempo_generation = MagicMock(return_value=(2, "2.x"))
        sl = _make_service_locator(tempo_svc=tempo)
        registered = _register_resources(BackendResources, sl)

        raw = await registered["tempo://server/capabilities"]()
        data = json.loads(raw)
        assert data["allow_write"] is False
        assert "toolsets" in data
        assert "query_policy" in data

    @pytest.mark.asyncio
    async def test_backends_resource(self):
        tempo = MagicMock()
        tempo.list_backends = AsyncMock(
            return_value=[{"id": "test", "type": "tempo", "health": "ready"}]
        )
        sl = _make_service_locator(tempo_svc=tempo)
        registered = _register_resources(BackendResources, sl)

        result = await registered["tempo://system/backends"]()
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["id"] == "test"

    @pytest.mark.asyncio
    async def test_schema_attributes_resource(self):
        tempo = MagicMock()
        tempo.detect_live_attributes = AsyncMock(
            return_value={
                "backend_id": "default",
                "total_attributes": 2,
                "scopes": {"resource": ["service.name"], "span": ["http.route"]},
            }
        )
        sl = _make_service_locator(tempo_svc=tempo)
        registered = _register_resources(BackendResources, sl)

        result = await registered["tempo://schema/{backend_id}/attributes"]("default")
        data = json.loads(result)
        assert data["total_attributes"] == 2
        assert "service.name" in data["scopes"]["resource"]

    @pytest.mark.asyncio
    async def test_overrides_resource(self):
        tempo = MagicMock()
        tempo.get_tenant_overrides = AsyncMock(
            return_value={
                "backend_id": "default",
                "tenant": "team-a",
                "overrides": {"max_bytes_per_trace": 5000000},
                "etag": '"v1"',
            }
        )
        sl = _make_service_locator(tempo_svc=tempo)
        registered = _register_resources(BackendResources, sl)

        result = await registered["tempo://overrides/{backend_id}/{tenant}"](
            "default", "team-a"
        )
        data = json.loads(result)
        assert data["etag"] == '"v1"'
        assert data["overrides"]["max_bytes_per_trace"] == 5000000


class TestDeploymentResources:
    """Verify live deployment overview and Kubernetes Operator resources."""

    @pytest.mark.asyncio
    async def test_operator_manifest_resource(self):
        k8s = MagicMock()
        k8s.get_tempo_operator_cr = AsyncMock(
            return_value={
                "kind": "TempoStack",
                "metadata": {"name": "tempo-prod", "namespace": "observability"},
            }
        )
        sl = _make_service_locator(k8s_svc=k8s)
        registered = _register_resources(DeploymentResources, sl)

        result = await registered["tempo://operator/manifests/{kind}/{namespace}/{name}"](
            "TempoStack", "observability", "tempo-prod"
        )
        data = json.loads(result)
        assert data["kind"] == "TempoStack"
        assert data["metadata"]["name"] == "tempo-prod"
