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


# ── Tests for _extract_container_port_from_pod_template ──────────────

class TestExtractContainerPort:
    """Test the static helper that auto-discovers containerPort from pod template."""

    def test_discovers_port_8080(self, generator_service):
        """Container port 8080 is correctly discovered."""
        pod_spec = {
            "containers": [
                {"name": "app", "ports": [{"containerPort": 8080}]}
            ]
        }
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 8080

    def test_discovers_port_9090(self, generator_service):
        """Container port 9090 is correctly discovered."""
        pod_spec = {
            "containers": [
                {"name": "app", "ports": [{"containerPort": 9090}]}
            ]
        }
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 9090

    def test_discovers_port_3000(self, generator_service):
        """Container port 3000 (Node.js apps) is correctly discovered."""
        pod_spec = {
            "containers": [
                {"name": "web", "ports": [{"name": "http", "containerPort": 3000}]}
            ]
        }
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 3000

    def test_returns_first_port_from_multiple(self, generator_service):
        """When container has multiple ports, the first one is returned."""
        pod_spec = {
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
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 8080

    def test_returns_first_container_port(self, generator_service):
        """When there are multiple containers, the first container's port wins."""
        pod_spec = {
            "containers": [
                {"name": "app", "ports": [{"containerPort": 8080}]},
                {"name": "sidecar", "ports": [{"containerPort": 15090}]},
            ]
        }
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 8080

    def test_skips_container_without_ports(self, generator_service):
        """First container has no ports, second does — second container's port is used."""
        pod_spec = {
            "containers": [
                {"name": "init", "image": "busybox"},
                {"name": "app", "ports": [{"containerPort": 9090}]},
            ]
        }
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 9090

    def test_defaults_to_80_when_no_ports(self, generator_service):
        """Container with no ports array → fallback to 80."""
        pod_spec = {
            "containers": [{"name": "app", "image": "nginx"}]
        }
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 80

    def test_defaults_to_80_when_empty_ports(self, generator_service):
        """Container with empty ports array → fallback to 80."""
        pod_spec = {
            "containers": [{"name": "app", "ports": []}]
        }
        assert generator_service._extract_container_port_from_pod_template(pod_spec) == 80

    def test_defaults_to_80_when_no_containers(self, generator_service):
        """Pod spec with no containers → fallback to 80."""
        assert generator_service._extract_container_port_from_pod_template({"containers": []}) == 80

    def test_defaults_to_80_when_none(self, generator_service):
        """None pod template spec → fallback to 80."""
        assert generator_service._extract_container_port_from_pod_template(None) == 80


# ── Tests for create_stable_canary_services with pod_template_spec ───

class TestCreateServicesPortAutoDiscovery:
    """Test that create_stable_canary_services auto-discovers targetPort from pod_template_spec."""

    @pytest.mark.asyncio
    async def test_auto_discovers_target_port_8080(self, generator_service):
        """When target_port=None and pod has containerPort 8080, Services use targetPort 8080."""
        pod_spec = {
            "containers": [
                {"name": "app", "ports": [{"containerPort": 8080}]}
            ]
        }
        result = await generator_service.create_stable_canary_services(
            app_name="hello-world",
            namespace="default",
            port=80,
            target_port=None,
            apply=False,
            strategy="bluegreen",
            pod_template_spec=pod_spec,
        )
        assert result["status"] == "success"
        # Parse the generated YAML to verify targetPort
        import yaml
        for yaml_key in ("stable_yaml", "canary_yaml"):
            svc = yaml.safe_load(result[yaml_key])
            for port in svc["spec"]["ports"]:
                assert port["targetPort"] == 8080, (
                    f"Expected targetPort 8080 in {yaml_key}, got {port['targetPort']}"
                )

    @pytest.mark.asyncio
    async def test_auto_discovers_target_port_9090(self, generator_service):
        """When target_port=None and pod has containerPort 9090, Services use targetPort 9090."""
        pod_spec = {
            "containers": [
                {"name": "app", "ports": [{"containerPort": 9090}]}
            ]
        }
        result = await generator_service.create_stable_canary_services(
            app_name="metrics-api",
            namespace="default",
            port=80,
            target_port=None,
            apply=False,
            strategy="canary",
            pod_template_spec=pod_spec,
        )
        assert result["status"] == "success"
        import yaml
        for yaml_key in ("stable_yaml", "canary_yaml"):
            svc = yaml.safe_load(result[yaml_key])
            for port in svc["spec"]["ports"]:
                assert port["targetPort"] == 9090

    @pytest.mark.asyncio
    async def test_explicit_target_port_overrides_pod_template(self, generator_service):
        """When target_port is explicitly provided, pod_template_spec is ignored."""
        pod_spec = {
            "containers": [
                {"name": "app", "ports": [{"containerPort": 8080}]}
            ]
        }
        result = await generator_service.create_stable_canary_services(
            app_name="hello-world",
            namespace="default",
            port=80,
            target_port=3000,  # explicit override
            apply=False,
            strategy="canary",
            pod_template_spec=pod_spec,
        )
        assert result["status"] == "success"
        import yaml
        for yaml_key in ("stable_yaml", "canary_yaml"):
            svc = yaml.safe_load(result[yaml_key])
            for port in svc["spec"]["ports"]:
                assert port["targetPort"] == 3000, (
                    f"Explicit target_port=3000 should override, got {port['targetPort']}"
                )

    @pytest.mark.asyncio
    async def test_no_pod_template_defaults_to_port(self, generator_service):
        """When target_port=None and no pod_template_spec, defaults to port value."""
        result = await generator_service.create_stable_canary_services(
            app_name="hello-world",
            namespace="default",
            port=80,
            target_port=None,
            apply=False,
            strategy="canary",
            pod_template_spec=None,
        )
        assert result["status"] == "success"
        import yaml
        for yaml_key in ("stable_yaml", "canary_yaml"):
            svc = yaml.safe_load(result[yaml_key])
            for port in svc["spec"]["ports"]:
                assert port["targetPort"] == 80

    @pytest.mark.asyncio
    async def test_pod_template_no_ports_defaults_to_port(self, generator_service):
        """When pod has no ports declared at all, falls back to port value."""
        pod_spec = {
            "containers": [{"name": "app", "image": "nginx"}]
        }
        result = await generator_service.create_stable_canary_services(
            app_name="hello-world",
            namespace="default",
            port=80,
            target_port=None,
            apply=False,
            strategy="canary",
            pod_template_spec=pod_spec,
        )
        assert result["status"] == "success"
        import yaml
        for yaml_key in ("stable_yaml", "canary_yaml"):
            svc = yaml.safe_load(result[yaml_key])
            for port in svc["spec"]["ports"]:
                assert port["targetPort"] == 80
