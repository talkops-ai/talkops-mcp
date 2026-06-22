"""Unit tests for backend discovery logic.

Covers §6.1: static config, K8s service labels, Tempo Operator CRDs,
and backend normalization.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo_mcp_server.config import BackendConfig, Config, ServerConfig, KubernetesConfig
from tempo_mcp_server.services.kubernetes_service import KubernetesService
from tempo_mcp_server.services.tempo_service import TempoService
from tempo_mcp_server.exceptions import TempoOperationError


class TestStaticConfigDiscovery:
    """Discovery from static environment configuration."""

    def test_single_backend_from_env(self):
        with patch.dict(os.environ, {
            "TEMPO_BASE_URL": "http://tempo:3200",
            "TEMPO_BACKEND_ID": "prod",
        }, clear=False):
            config = Config.from_env()
            assert config.backends[0].id == "prod"
            assert config.backends[0].base_url == "http://tempo:3200"

    def test_multi_backend_from_json_env(self):
        backends = [
            {"id": "prod", "base_url": "http://tempo-prod:3200", "multi_tenant": True},
            {"id": "staging", "base_url": "http://tempo-staging:3200"},
        ]
        with patch.dict(os.environ, {"TEMPO_BACKENDS": json.dumps(backends)}, clear=False):
            config = Config.from_env()
            assert len(config.backends) == 2
            assert config.backends[0].multi_tenant is True
            assert config.backends[1].multi_tenant is False

    def test_invalid_json_falls_back_to_default(self):
        with patch.dict(os.environ, {"TEMPO_BACKENDS": "not-valid-json"}, clear=False):
            config = Config.from_env()
            assert len(config.backends) == 1
            assert config.backends[0].id == "default"


class TestBackendNormalization:
    """Verify BackendConfig defaults and normalization."""

    def test_defaults(self):
        b = BackendConfig()
        assert b.id == "default"
        assert b.base_url == "http://localhost:3200"
        assert b.type == "tempo"
        assert b.multi_tenant is False
        assert b.tenant_header == "X-Scope-OrgID"
        assert b.llm_format_supported is True

    def test_multi_tenant_backend(self):
        b = BackendConfig(id="mt", multi_tenant=True, default_tenant="org-1")
        assert b.multi_tenant is True
        assert b.default_tenant == "org-1"

    def test_deployment_modes(self):
        from typing import Literal, cast
        for mode in ["monolithic", "microservices", "unknown"]:
            typed_mode = cast(Literal["monolithic", "microservices", "unknown"], mode)
            b = BackendConfig(deployment_mode=typed_mode)
            assert b.deployment_mode == mode


class TestBackendResolution:
    """TempoService backend lookup."""

    def test_default_backend_id(self, tempo_service):
        assert tempo_service.get_default_backend_id() == "test-backend"

    def test_unknown_backend_raises(self, tempo_service):
        with pytest.raises(TempoOperationError, match="Unknown backend"):
            tempo_service._get_backend("nonexistent")


class TestKubernetesDiscovery:
    """Discovery from Kubernetes service labels and Operator CRDs."""

    @pytest.mark.asyncio
    async def test_discover_tempo_services(self, mock_kubernetes_api):
        k8s_svc = KubernetesService(KubernetesConfig(enabled=True))
        k8s_svc._api_client = mock_kubernetes_api
        k8s_svc._k8s_loaded = True

        backends = await k8s_svc.discover_tempo_services(namespace="monitoring")
        assert len(backends) == 1
        assert backends[0].id == "k8s-monitoring-tempo-prod"
        assert "tempo-prod.monitoring.svc.cluster.local" in backends[0].base_url

    # §11 #8: test_backend_discovery_from_tempo_operator_cr
    @pytest.mark.asyncio
    async def test_discover_tempo_operator_crs(self):
        k8s_svc = KubernetesService(KubernetesConfig(enabled=True))

        mock_custom_api = MagicMock()
        cr_item = {
            "metadata": {"name": "prod-tempo", "namespace": "tracing"},
        }
        mock_custom_api.list_namespaced_custom_object.return_value = {"items": [cr_item]}

        # Build the mock: `from kubernetes import client as k8s_client`
        # requires kubernetes.client to have .CustomObjectsApi
        mock_k8s_client = MagicMock()
        mock_k8s_client.CustomObjectsApi.return_value = mock_custom_api

        mock_k8s_package = MagicMock()
        mock_k8s_package.client = mock_k8s_client

        import sys
        # Remove cached modules so the `from kubernetes import client` inside the function re-imports
        saved = {}
        for key in list(sys.modules.keys()):
            if key.startswith("kubernetes"):
                saved[key] = sys.modules.pop(key)

        sys.modules["kubernetes"] = mock_k8s_package
        sys.modules["kubernetes.client"] = mock_k8s_client
        try:
            backends = await k8s_svc.discover_tempo_operator_crs(namespace="tracing")
        finally:
            # Restore original state
            for key in list(sys.modules.keys()):
                if key.startswith("kubernetes"):
                    del sys.modules[key]
            sys.modules.update(saved)

        assert len(backends) >= 1
        assert "operator-tracing-prod-tempo" in backends[0].id

    @pytest.mark.asyncio
    async def test_disabled_k8s_returns_empty(self):
        k8s_svc = KubernetesService(KubernetesConfig(enabled=False))
        backends = await k8s_svc.discover_tempo_services()
        assert backends == []
