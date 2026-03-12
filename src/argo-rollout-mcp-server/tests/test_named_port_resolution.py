"""Tests for named targetPort resolution in create_rollout_services_cloned.

Verifies the fix for the named-port issue where cloned Services copy a named
targetPort (e.g. "http") from the original Service.  If the Rollout's pod
template later loses its ports array (ArgoCD/Helm overwrite), Kubernetes cannot
resolve the name and traffic routing breaks.

The fix resolves named ports to their numeric containerPort values at Service
creation time using the Deployment's pod template.
"""

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from argo_rollout_mcp_server.services.generator_service import GeneratorService


# ── Helpers ──────────────────────────────────────────────────────────

def _make_v1_service_port(name, port, target_port, protocol="TCP"):
    """Simulate a kubernetes.client.V1ServicePort object."""
    return SimpleNamespace(
        name=name,
        port=port,
        target_port=target_port,
        protocol=protocol,
        node_port=None,
    )


def _make_original_service(ports, selector=None, labels=None, svc_name="hello-world"):
    """Build a mock V1Service with the given ports."""
    return SimpleNamespace(
        metadata=SimpleNamespace(name=svc_name, labels=labels or {"app": "hello-world"}),
        spec=SimpleNamespace(
            ports=ports,
            selector=selector or {"app": "hello-world"},
        ),
    )


# ── Tests ────────────────────────────────────────────────────────────

@pytest.fixture
def generator_service():
    """Create a GeneratorService without k8s config."""
    svc = GeneratorService.__new__(GeneratorService)
    svc.config = None
    svc._apps_v1 = None
    return svc


class TestNamedPortResolution:
    """Test that create_rollout_services_cloned resolves named targetPort."""

    @pytest.mark.asyncio
    async def test_named_port_resolved_to_numeric(self, generator_service):
        """Named targetPort 'http' + pod template port name 'http'=80 → targetPort=80."""
        original_svc = _make_original_service(
            ports=[_make_v1_service_port("http", 80, "http")]
        )
        pod_template = {
            "containers": [
                {
                    "name": "app",
                    "ports": [{"name": "http", "containerPort": 80}],
                }
            ]
        }

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="bluegreen",
                pod_template=pod_template,
            )

        assert result["services_created"] or result["services_already_existed"]
        # Verify the V1ServicePort was constructed with numeric target_port
        calls = mock_core.return_value.create_namespaced_service.call_args_list
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            for port_spec in svc_body.spec.ports:
                assert port_spec.target_port == 80, (
                    f"Expected numeric targetPort 80, got {port_spec.target_port}"
                )

    @pytest.mark.asyncio
    async def test_named_port_non_standard_container_port(self, generator_service):
        """Named targetPort 'http' + pod template port 'http'=8080 → targetPort=8080."""
        original_svc = _make_original_service(
            ports=[_make_v1_service_port("http", 80, "http")]
        )
        pod_template = {
            "containers": [
                {
                    "name": "app",
                    "ports": [{"name": "http", "containerPort": 8080}],
                }
            ]
        }

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="bluegreen",
                pod_template=pod_template,
            )

        calls = mock_core.return_value.create_namespaced_service.call_args_list
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            for port_spec in svc_body.spec.ports:
                assert port_spec.target_port == 8080, (
                    f"Expected targetPort 8080, got {port_spec.target_port}"
                )

    @pytest.mark.asyncio
    async def test_named_port_fallback_when_no_pod_template(self, generator_service):
        """Named targetPort 'http' + no pod_template → falls back to service port."""
        original_svc = _make_original_service(
            ports=[_make_v1_service_port("http", 80, "http")]
        )

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="canary",
                pod_template=None,
            )

        calls = mock_core.return_value.create_namespaced_service.call_args_list
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            for port_spec in svc_body.spec.ports:
                # Falls back to p.port (80) since no pod_template
                assert port_spec.target_port == 80, (
                    f"Expected fallback targetPort 80, got {port_spec.target_port}"
                )

    @pytest.mark.asyncio
    async def test_named_port_not_in_pod_template(self, generator_service):
        """Named targetPort 'grpc' not in pod template → falls back to service port."""
        original_svc = _make_original_service(
            ports=[_make_v1_service_port("grpc", 9090, "grpc")]
        )
        pod_template = {
            "containers": [
                {
                    "name": "app",
                    "ports": [{"name": "http", "containerPort": 80}],
                }
            ]
        }

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="canary",
                pod_template=pod_template,
            )

        calls = mock_core.return_value.create_namespaced_service.call_args_list
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            for port_spec in svc_body.spec.ports:
                # Falls back to p.port (9090) since "grpc" isn't in pod_template
                assert port_spec.target_port == 9090, (
                    f"Expected fallback targetPort 9090, got {port_spec.target_port}"
                )

    @pytest.mark.asyncio
    async def test_numeric_target_port_unchanged(self, generator_service):
        """Numeric targetPort 80 stays 80 regardless of pod_template."""
        original_svc = _make_original_service(
            ports=[_make_v1_service_port("http", 80, 80)]
        )
        pod_template = {
            "containers": [
                {
                    "name": "app",
                    "ports": [{"name": "http", "containerPort": 8080}],
                }
            ]
        }

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="canary",
                pod_template=pod_template,
            )

        calls = mock_core.return_value.create_namespaced_service.call_args_list
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            for port_spec in svc_body.spec.ports:
                assert port_spec.target_port == 80, (
                    f"Expected unchanged targetPort 80, got {port_spec.target_port}"
                )

    @pytest.mark.asyncio
    async def test_multiple_named_ports_resolved(self, generator_service):
        """Multiple named ports are all resolved correctly."""
        original_svc = _make_original_service(
            ports=[
                _make_v1_service_port("http", 80, "http"),
                _make_v1_service_port("metrics", 9090, "metrics"),
            ]
        )
        pod_template = {
            "containers": [
                {
                    "name": "app",
                    "ports": [
                        {"name": "http", "containerPort": 8080},
                        {"name": "metrics", "containerPort": 9090},
                    ],
                }
            ]
        }

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="bluegreen",
                pod_template=pod_template,
            )

        calls = mock_core.return_value.create_namespaced_service.call_args_list
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            ports = svc_body.spec.ports
            assert ports[0].target_port == 8080, f"http should resolve to 8080"
            assert ports[1].target_port == 9090, f"metrics should resolve to 9090"

    @pytest.mark.asyncio
    async def test_empty_pod_template_containers(self, generator_service):
        """Pod template with no containers → falls back to service port."""
        original_svc = _make_original_service(
            ports=[_make_v1_service_port("http", 80, "http")]
        )
        pod_template = {"containers": []}

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="canary",
                pod_template=pod_template,
            )

        calls = mock_core.return_value.create_namespaced_service.call_args_list
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            for port_spec in svc_body.spec.ports:
                assert port_spec.target_port == 80

    @pytest.mark.asyncio
    async def test_bluegreen_creates_active_preview_services(self, generator_service):
        """Bluegreen strategy with named port creates active+preview services."""
        original_svc = _make_original_service(
            ports=[_make_v1_service_port("http", 80, "http")]
        )
        pod_template = {
            "containers": [
                {"name": "app", "ports": [{"name": "http", "containerPort": 80}]}
            ]
        }

        with patch("kubernetes.client.CoreV1Api") as mock_core:
            mock_core.return_value.create_namespaced_service = MagicMock()
            result = await generator_service.create_rollout_services_cloned(
                original_service=original_svc,
                app_name="hello-world",
                namespace="default",
                strategy="bluegreen",
                pod_template=pod_template,
            )

        # Verify both "active" and "preview" services were created
        calls = mock_core.return_value.create_namespaced_service.call_args_list
        created_names = []
        for call in calls:
            svc_body = call.kwargs.get("body") or call[1].get("body")
            created_names.append(svc_body.metadata.name)
        assert "hello-world-active" in created_names
        assert "hello-world-preview" in created_names
