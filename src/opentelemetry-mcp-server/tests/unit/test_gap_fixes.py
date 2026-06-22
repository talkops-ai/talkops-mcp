"""Unit tests for operator diagnostics, env var remediation, and service health.

Tests the three new KubernetesService methods added for Gaps 2-4:
- get_operator_diagnostics()
- strip_otel_env_vars()
- get_collector_service_health()
"""

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_k8s_service(
    mock_core_v1=None,
    mock_apps_v1=None,
    mock_custom_api=None,
) -> KubernetesService:
    """Create a KubernetesService with mocked K8s clients.

    Bypasses __init__ entirely and injects mock API clients directly.
    """
    svc = object.__new__(KubernetesService)

    # Minimal config
    from opentelemetry_mcp_server.config import KubernetesConfig, OtelOperatorConfig
    svc._k8s_config = KubernetesConfig(enabled=True)
    svc._otel_config = OtelOperatorConfig()
    svc._initialized = True

    svc._core_v1 = mock_core_v1 or MagicMock()
    svc._apps_v1 = mock_apps_v1 or MagicMock()
    svc._custom_api = mock_custom_api or MagicMock()

    return svc


def _mock_pod(name: str, namespace: str, phase: str = "Running"):
    """Create a minimal mock V1Pod."""
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = namespace
    pod.status.phase = phase
    return pod


def _mock_pod_list(*pods):
    """Create a mock V1PodList."""
    result = MagicMock()
    result.items = list(pods)
    return result


def _mock_service(name: str, selector: Dict[str, str]):
    """Create a minimal mock V1Service."""
    svc = MagicMock()
    svc.metadata.name = name
    svc.spec.selector = selector
    return svc


def _mock_endpoints(ready_count: int = 3, not_ready_count: int = 0):
    """Create a minimal mock V1Endpoints."""
    ep = MagicMock()

    if ready_count == 0 and not_ready_count == 0:
        ep.subsets = None
        return ep

    subset = MagicMock()
    subset.addresses = [MagicMock() for _ in range(ready_count)] if ready_count else None
    subset.not_ready_addresses = [MagicMock() for _ in range(not_ready_count)] if not_ready_count else None
    ep.subsets = [subset]
    return ep


# ──────────────────────────────────────────────
# get_operator_diagnostics tests (Gap 2)
# ──────────────────────────────────────────────

class TestGetOperatorDiagnostics:
    """Tests for KubernetesService.get_operator_diagnostics()."""

    @pytest.mark.asyncio
    async def test_operator_found_and_healthy(self):
        """Happy path: operator pod found, logs read, no errors."""
        mock_core = MagicMock()
        pod = _mock_pod(
            "opentelemetry-operator-controller-manager-abc12",
            "opentelemetry-operator-system",
        )
        mock_core.list_namespaced_pod.return_value = _mock_pod_list(pod)
        mock_core.read_namespaced_pod_log.return_value = (
            "2025-05-24T10:00:00Z INFO Starting reconciler\n"
            "2025-05-24T10:00:01Z INFO Reconciled collector my-collector\n"
        )

        svc = _make_k8s_service(mock_core_v1=mock_core)
        # Mock list_instrumentations and list_namespaces
        svc.list_instrumentations = AsyncMock(return_value={"items": []})
        svc.list_namespaces = AsyncMock(return_value=["default"])

        result = await svc.get_operator_diagnostics()

        assert result["operator_found"] is True
        assert result["operator_status"] == "Running"
        assert result["recent_errors"] == []  # No error keywords

    @pytest.mark.asyncio
    async def test_operator_not_found(self):
        """Operator pod not found in any namespace."""
        mock_core = MagicMock()
        mock_core.list_namespaced_pod.return_value = _mock_pod_list()  # empty

        svc = _make_k8s_service(mock_core_v1=mock_core)

        result = await svc.get_operator_diagnostics()

        assert result["operator_found"] is False
        assert any("not found" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_detects_error_in_logs(self):
        """Error keywords in logs are extracted."""
        mock_core = MagicMock()
        pod = _mock_pod("op-pod", "opentelemetry-operator-system")
        mock_core.list_namespaced_pod.return_value = _mock_pod_list(pod)
        mock_core.read_namespaced_pod_log.return_value = (
            "2025-05-24T10:00:00Z INFO Starting\n"
            "2025-05-24T10:00:01Z ERROR Failed to reconcile collector\n"
            "2025-05-24T10:00:02Z FATAL panic in webhook handler\n"
        )

        svc = _make_k8s_service(mock_core_v1=mock_core)
        svc.list_instrumentations = AsyncMock(return_value={"items": []})
        svc.list_namespaces = AsyncMock(return_value=[])

        result = await svc.get_operator_diagnostics()

        assert len(result["recent_errors"]) == 2
        assert any("ERROR" in e for e in result["recent_errors"])
        assert any("FATAL" in e for e in result["recent_errors"])

    @pytest.mark.asyncio
    async def test_detects_multiple_instrumentation_warning(self):
        """Detects 'multiple Instrumentation instances' from log text."""
        mock_core = MagicMock()
        pod = _mock_pod("op-pod", "opentelemetry-operator-system")
        mock_core.list_namespaced_pod.return_value = _mock_pod_list(pod)
        mock_core.read_namespaced_pod_log.return_value = (
            "ERROR multiple OpenTelemetry Instrumentation instances found in namespace otel-demo\n"
        )

        svc = _make_k8s_service(mock_core_v1=mock_core)
        svc.list_instrumentations = AsyncMock(return_value={"items": [{}, {}]})
        svc.list_namespaces = AsyncMock(return_value=["otel-demo"])

        result = await svc.get_operator_diagnostics()

        assert any("multiple" in w.lower() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_counts_instrumentation_crs_per_namespace(self):
        """Reports per-namespace Instrumentation CRD counts."""
        mock_core = MagicMock()
        pod = _mock_pod("op-pod", "opentelemetry-operator-system")
        mock_core.list_namespaced_pod.return_value = _mock_pod_list(pod)
        mock_core.read_namespaced_pod_log.return_value = "INFO all good"

        svc = _make_k8s_service(mock_core_v1=mock_core)
        svc.list_namespaces = AsyncMock(return_value=["ns-a", "ns-b"])
        svc.list_instrumentations = AsyncMock(
            side_effect=[
                {"items": [{"metadata": {"name": "instr-1"}}]},  # ns-a: 1
                {"items": [{"metadata": {"name": "i1"}}, {"metadata": {"name": "i2"}}]},  # ns-b: 2
            ]
        )

        result = await svc.get_operator_diagnostics()

        assert result["instrumentation_cr_counts"]["ns-a"] == 1
        assert result["instrumentation_cr_counts"]["ns-b"] == 2
        assert any("ns-b" in w and "2" in w for w in result["warnings"])


# ──────────────────────────────────────────────
# strip_otel_env_vars tests (Gap 3)
# ──────────────────────────────────────────────

class TestStripOtelEnvVars:
    """Tests for KubernetesService.strip_otel_env_vars()."""

    @pytest.mark.asyncio
    async def test_dry_run_shows_what_would_be_removed(self):
        """Dry run lists conflicting vars without modifying."""
        svc = _make_k8s_service()
        svc.get_deployment = AsyncMock(return_value={
            "containers": [
                {
                    "name": "recommendation-server",
                    "image": "otel-demo:latest",
                    "env": {
                        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://old:4317",
                        "OTEL_COLLECTOR_NAME": "old-collector",
                        "APP_PORT": "8080",
                    },
                },
            ],
        })

        result = await svc.strip_otel_env_vars(
            namespace="otel-demo",
            deployment_name="recommendation",
            dry_run=True,
        )

        assert result["action"] == "dry_run"
        assert "recommendation-server" in result["would_remove"]
        assert "OTEL_EXPORTER_OTLP_ENDPOINT" in result["would_remove"]["recommendation-server"]
        assert "APP_PORT" not in str(result["would_remove"])

    @pytest.mark.asyncio
    async def test_no_change_when_no_conflicts(self):
        """No conflicting env vars => no_change action."""
        svc = _make_k8s_service()
        svc.get_deployment = AsyncMock(return_value={
            "containers": [
                {
                    "name": "app",
                    "image": "app:latest",
                    "env": {"APP_PORT": "8080"},
                },
            ],
        })

        result = await svc.strip_otel_env_vars(
            namespace="default",
            deployment_name="app",
        )

        assert result["action"] == "no_change"

    @pytest.mark.asyncio
    async def test_apply_patches_deployment(self):
        """With dry_run=False, patches the deployment."""
        mock_apps = MagicMock()
        svc = _make_k8s_service(mock_apps_v1=mock_apps)
        svc.get_deployment = AsyncMock(return_value={
            "containers": [
                {
                    "name": "server",
                    "image": "app:latest",
                    "env": {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://old:4317"},
                },
            ],
        })

        result = await svc.strip_otel_env_vars(
            namespace="otel-demo",
            deployment_name="recommendation",
            dry_run=False,
        )

        assert result["action"] == "applied"
        assert "server" in result["removed"]
        # Verify patch_namespaced_deployment was called
        mock_apps.patch_namespaced_deployment.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_init_containers(self):
        """Init containers are not scanned for env vars."""
        svc = _make_k8s_service()
        svc.get_deployment = AsyncMock(return_value={
            "containers": [
                {
                    "name": "app",
                    "image": "app:latest",
                    "env": {"APP_PORT": "8080"},
                },
                {
                    "name": "otel-init",
                    "image": "otel-init:latest",
                    "env": {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://old:4317"},
                    "is_init_container": True,
                },
            ],
        })

        result = await svc.strip_otel_env_vars(
            namespace="default",
            deployment_name="app",
        )

        assert result["action"] == "no_change"


# ──────────────────────────────────────────────
# get_collector_service_health tests (Gap 4)
# ──────────────────────────────────────────────

class TestGetCollectorServiceHealth:
    """Tests for KubernetesService.get_collector_service_health()."""

    @pytest.mark.asyncio
    async def test_healthy_service_with_ready_endpoints(self):
        """Service found with ready endpoints."""
        mock_core = MagicMock()
        mock_core.read_namespaced_service.return_value = _mock_service(
            "my-collector-collector",
            {"app.kubernetes.io/name": "my-collector"},
        )
        mock_core.read_namespaced_endpoints.return_value = _mock_endpoints(
            ready_count=3, not_ready_count=0
        )

        svc = _make_k8s_service(mock_core_v1=mock_core)
        result = await svc.get_collector_service_health(
            namespace="observability",
            collector_name="my-collector",
        )

        assert result["service_found"] is True
        assert result["service_name"] == "my-collector-collector"
        assert result["ready_endpoints"] == 3
        assert result["warnings"] == []

    @pytest.mark.asyncio
    async def test_service_not_found(self):
        """No service found for collector."""
        mock_core = MagicMock()
        mock_core.read_namespaced_service.side_effect = Exception("NotFound")

        svc = _make_k8s_service(mock_core_v1=mock_core)
        result = await svc.get_collector_service_health(
            namespace="observability",
            collector_name="missing",
        )

        assert result["service_found"] is False
        assert any("No K8s Service found" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_zero_ready_with_not_ready_endpoints(self):
        """Service exists but all endpoints not-ready -> critical warning."""
        mock_core = MagicMock()
        mock_core.read_namespaced_service.return_value = _mock_service(
            "my-collector-collector",
            {"app.kubernetes.io/name": "my-collector"},
        )
        mock_core.read_namespaced_endpoints.return_value = _mock_endpoints(
            ready_count=0, not_ready_count=2
        )

        svc = _make_k8s_service(mock_core_v1=mock_core)
        result = await svc.get_collector_service_health(
            namespace="observability",
            collector_name="my-collector",
        )

        assert result["ready_endpoints"] == 0
        assert result["not_ready_endpoints"] == 2
        assert any("CRITICAL" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_zero_total_endpoints_orphaned_selector(self):
        """No endpoints at all -> orphaned selector warning."""
        mock_core = MagicMock()
        mock_core.read_namespaced_service.return_value = _mock_service(
            "my-collector-collector",
            {"app.kubernetes.io/name": "deleted-collector"},
        )
        mock_core.read_namespaced_endpoints.return_value = _mock_endpoints(
            ready_count=0, not_ready_count=0
        )

        svc = _make_k8s_service(mock_core_v1=mock_core)
        result = await svc.get_collector_service_health(
            namespace="observability",
            collector_name="my-collector",
        )

        assert result["ready_endpoints"] == 0
        assert any("orphaned" in w.lower() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_falls_back_to_collector_name_without_suffix(self):
        """If {name}-collector not found, tries {name}."""
        mock_core = MagicMock()
        # First call with -collector suffix -> fail
        # Second call with just name -> succeed
        mock_core.read_namespaced_service.side_effect = [
            Exception("NotFound"),  # my-collector-collector
            _mock_service("my-collector", {"app": "collector"}),  # my-collector
        ]
        mock_core.read_namespaced_endpoints.return_value = _mock_endpoints(ready_count=1)

        svc = _make_k8s_service(mock_core_v1=mock_core)
        result = await svc.get_collector_service_health(
            namespace="observability",
            collector_name="my-collector",
        )

        assert result["service_found"] is True
        assert result["service_name"] == "my-collector"
