"""Unit tests for KubernetesService helper methods and guard logic.

Tests internal conversion methods and availability checks directly
without any MCP protocol or K8s cluster dependency.
"""

import pytest
from unittest.mock import MagicMock

from opentelemetry_mcp_server.config import KubernetesConfig, OtelOperatorConfig
from opentelemetry_mcp_server.exceptions import OtelConnectionError
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService


class TestEnsureAvailable:
    """Test the _ensure_available guard."""

    def test_raises_when_disabled(self):
        """When K8s is disabled, all operations must raise."""
        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = KubernetesConfig(enabled=False)
        svc._initialized = False
        with pytest.raises(OtelConnectionError, match="not available"):
            svc._ensure_available()

    def test_raises_when_not_initialized(self):
        """When client failed to init, operations must raise."""
        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = KubernetesConfig(enabled=True)
        svc._initialized = False
        with pytest.raises(OtelConnectionError, match="not available"):
            svc._ensure_available()

    def test_passes_when_available(self):
        """When enabled and initialized, should not raise."""
        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = KubernetesConfig(enabled=True)
        svc._initialized = True
        svc._ensure_available()  # Should not raise


class TestIsAvailable:
    """Test the is_available property."""

    def test_available_when_enabled_and_initialized(self):
        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = KubernetesConfig(enabled=True)
        svc._initialized = True
        assert svc.is_available is True

    def test_not_available_when_disabled(self):
        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = KubernetesConfig(enabled=False)
        svc._initialized = True
        assert svc.is_available is False

    def test_not_available_when_not_initialized(self):
        svc = KubernetesService.__new__(KubernetesService)
        svc._k8s_config = KubernetesConfig(enabled=True)
        svc._initialized = False
        assert svc.is_available is False


class TestDeploymentToDict:
    """Test the _deployment_to_dict static helper."""

    def _make_deployment_mock(
        self,
        name="my-deploy",
        namespace="default",
        replicas=3,
        ready_replicas=2,
        annotations=None,
        pod_annotations=None,
        containers=None,
        init_containers=None,
    ):
        dep = MagicMock()
        dep.metadata.name = name
        dep.metadata.namespace = namespace
        dep.metadata.labels = {"app": "test"}
        dep.metadata.annotations = annotations or {}
        dep.spec.replicas = replicas
        dep.status.ready_replicas = ready_replicas

        # Pod template
        dep.spec.template.metadata.annotations = pod_annotations or {}

        if containers is None:
            container = MagicMock()
            container.name = "app"
            container.image = "my-image:latest"
            container.env = []
            containers = [container]
        dep.spec.template.spec.containers = containers
        dep.spec.template.spec.init_containers = init_containers or []

        return dep

    def test_basic_deployment(self):
        dep = self._make_deployment_mock()
        result = KubernetesService._deployment_to_dict(dep)
        assert result["name"] == "my-deploy"
        assert result["namespace"] == "default"
        assert result["kind"] == "Deployment"
        assert result["replicas"] == 3
        assert result["ready_replicas"] == 2

    def test_deployment_with_pod_annotations(self):
        dep = self._make_deployment_mock(
            pod_annotations={"instrumentation.opentelemetry.io/inject-java": "true"}
        )
        result = KubernetesService._deployment_to_dict(dep)
        assert "inject-java" in str(result["pod_annotations"])

    def test_deployment_with_init_container(self):
        init_container = MagicMock()
        init_container.name = "otel-agent"
        init_container.image = "otel/autoinstrumentation-java:latest"
        dep = self._make_deployment_mock(init_containers=[init_container])
        result = KubernetesService._deployment_to_dict(dep)
        init_containers = [c for c in result["containers"] if c.get("is_init_container")]
        assert len(init_containers) == 1
        assert init_containers[0]["name"] == "otel-agent"

    def test_deployment_with_env_vars(self):
        container = MagicMock()
        container.name = "app"
        container.image = "my-image"
        env1 = MagicMock()
        env1.name = "OTEL_EXPORTER_OTLP_ENDPOINT"
        env1.value = "http://otel-collector:4317"
        env2 = MagicMock()
        env2.name = "OTEL_SERVICE_NAME"
        env2.value = "my-service"
        container.env = [env1, env2]
        dep = self._make_deployment_mock(containers=[container])
        result = KubernetesService._deployment_to_dict(dep)
        app_container = result["containers"][0]
        assert app_container["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4317"

    def test_deployment_no_status(self):
        dep = self._make_deployment_mock()
        dep.status = None
        result = KubernetesService._deployment_to_dict(dep)
        assert result["ready_replicas"] == 0


class TestPodToDict:
    """Test the _pod_to_dict static helper."""

    def _make_pod_mock(
        self,
        name="test-pod",
        namespace="default",
        node_name="node-1",
        phase="Running",
        privileged=False,
        host_pid=False,
        capabilities=None,
        host_path_volumes=None,
    ):
        pod = MagicMock()
        pod.metadata.name = name
        pod.metadata.namespace = namespace
        pod.metadata.labels = {"app": "test"}
        pod.metadata.annotations = {}
        pod.spec.node_name = node_name
        pod.spec.host_pid = host_pid
        pod.status.phase = phase

        # Containers
        container = MagicMock()
        container.name = "app"
        container.image = "my-image"
        container.security_context.privileged = privileged
        container.security_context.capabilities = MagicMock()
        container.security_context.capabilities.add = capabilities or []
        container.volume_mounts = []
        pod.spec.containers = [container]

        # Volumes
        pod.spec.volumes = []
        if host_path_volumes:
            for hp in host_path_volumes:
                vol = MagicMock()
                vol.name = hp["name"]
                vol.host_path.path = hp["path"]
                pod.spec.volumes.append(vol)

        return pod

    def test_basic_pod(self):
        pod = self._make_pod_mock()
        result = KubernetesService._pod_to_dict(pod)
        assert result["name"] == "test-pod"
        assert result["namespace"] == "default"
        assert result["phase"] == "Running"
        assert result["node_name"] == "node-1"

    def test_privileged_pod(self):
        pod = self._make_pod_mock(privileged=True)
        result = KubernetesService._pod_to_dict(pod)
        sc = result["containers"][0]["security_context"]
        assert sc["privileged"] is True

    def test_host_pid_pod(self):
        pod = self._make_pod_mock(host_pid=True)
        result = KubernetesService._pod_to_dict(pod)
        assert result["host_pid"] is True

    def test_pod_with_capabilities(self):
        pod = self._make_pod_mock(capabilities=["BPF", "PERFMON", "SYS_PTRACE"])
        result = KubernetesService._pod_to_dict(pod)
        caps = result["containers"][0]["security_context"]["capabilities"]
        assert "BPF" in caps
        assert "PERFMON" in caps

    def test_pod_with_host_volumes(self):
        pod = self._make_pod_mock(
            host_path_volumes=[
                {"name": "host-sys", "path": "/sys"},
                {"name": "host-proc", "path": "/proc"},
            ]
        )
        result = KubernetesService._pod_to_dict(pod)
        assert len(result["host_volumes"]) == 2
        paths = [hv["host_path"] for hv in result["host_volumes"]]
        assert "/sys" in paths
        assert "/proc" in paths

    def test_pod_no_status(self):
        pod = self._make_pod_mock()
        pod.status = None
        result = KubernetesService._pod_to_dict(pod)
        assert result["phase"] == "Unknown"
