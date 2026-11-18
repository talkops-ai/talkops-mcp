"""T-U4: Unit tests for generic workload operations across Deployment, StatefulSet, and DaemonSet."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from opentelemetry_mcp_server.config import KubernetesConfig
from opentelemetry_mcp_server.services.kubernetes_service import KubernetesService


def _make_mock_k8s() -> tuple[KubernetesService, MagicMock]:
    svc = KubernetesService(KubernetesConfig(enabled=False))
    svc._k8s_config = KubernetesConfig(enabled=True)
    svc._initialized = True
    mock_apps = MagicMock()
    svc._apps_v1 = mock_apps
    return svc, mock_apps


def _fake_k8s_workload_obj(name: str):
    obj = MagicMock()
    obj.metadata.name = name
    obj.metadata.namespace = "prod"
    obj.metadata.labels = {"app": name}
    obj.metadata.annotations = {}
    obj.spec.replicas = 2
    obj.spec.template.metadata.annotations = {"instrumentation.opentelemetry.io/inject-java": "true"}
    obj.spec.template.spec.containers = []
    obj.spec.template.spec.init_containers = []
    obj.status.ready_replicas = 2
    obj.status.available_replicas = 2
    obj.status.number_ready = 2
    obj.status.desired_number_scheduled = 2
    return obj


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "read_method", "patch_method"),
    [
        ("Deployment", "read_namespaced_deployment", "patch_namespaced_deployment"),
        ("StatefulSet", "read_namespaced_stateful_set", "patch_namespaced_stateful_set"),
        ("DaemonSet", "read_namespaced_daemon_set", "patch_namespaced_daemon_set"),
    ],
)
async def test_get_patch_and_restart_across_workload_kinds(kind: str, read_method: str, patch_method: str):
    svc, mock_apps = _make_mock_k8s()
    fake_obj = _fake_k8s_workload_obj(f"my-{kind.lower()}")
    getattr(mock_apps, read_method).return_value = fake_obj
    getattr(mock_apps, patch_method).return_value = fake_obj

    got = await svc.get_workload("prod", f"my-{kind.lower()}", kind=kind)
    assert got["kind"] == kind
    assert got["name"] == f"my-{kind.lower()}"

    patched = await svc.patch_workload_annotations(
        namespace="prod",
        name=f"my-{kind.lower()}",
        annotations={"instrumentation.opentelemetry.io/inject-java": None},
        kind=kind,
        dry_run=True,
    )
    assert patched["kind"] == kind
    getattr(mock_apps, patch_method).assert_called_once()

    restarted = await svc.restart_workload("prod", f"my-{kind.lower()}", kind=kind, dry_run=True)
    assert restarted["kind"] == kind
