"""Unit tests for ArgoRolloutsService safety guards (T-U6)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from argo_rollout_mcp_server.config import ServerConfig
from argo_rollout_mcp_server.exceptions.custom import ArgoRolloutError
from argo_rollout_mcp_server.services.argo_rollouts_service import ArgoRolloutsService


def _make_service() -> ArgoRolloutsService:
    svc = ArgoRolloutsService(ServerConfig())
    svc._initialized = True
    svc._rollout_api = MagicMock()
    svc._apps_v1 = MagicMock()
    svc._analysis_template_api = MagicMock()
    svc._cluster_analysis_template_api = MagicMock()
    return svc


@pytest.mark.asyncio
async def test_workload_ref_delete_safety_blocks_when_deployment_scaled_to_zero():
    svc = _make_service()
    rollout = MagicMock()
    rollout.to_dict.return_value = {
        "spec": {
            "workloadRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": "legacy-app",
                "scaleDown": "onsuccess",
            }
        }
    }
    svc._rollout_api.get.return_value = rollout

    dep = MagicMock()
    dep.spec.replicas = 0
    dep.status.ready_replicas = 0
    svc._apps_v1.read_namespaced_deployment.return_value = dep

    with pytest.raises(ArgoRolloutError, match="scaled to 0 replicas"):
        await svc.check_workload_ref_delete_safety(name="legacy-app", namespace="default")


@pytest.mark.asyncio
async def test_workload_ref_delete_safety_allows_when_deployment_has_ready_replicas():
    svc = _make_service()
    rollout = MagicMock()
    rollout.to_dict.return_value = {
        "spec": {
            "workloadRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": "legacy-app",
            }
        }
    }
    svc._rollout_api.get.return_value = rollout

    dep = MagicMock()
    dep.spec.replicas = 3
    dep.status.ready_replicas = 3
    svc._apps_v1.read_namespaced_deployment.return_value = dep

    await svc.check_workload_ref_delete_safety(name="legacy-app", namespace="default")


@pytest.mark.asyncio
async def test_verify_rollout_healthy_blocks_when_degraded():
    svc = _make_service()
    svc.get_rollout_status = AsyncMock(
        return_value={
            "phase": "Degraded",
            "desired_replicas": 3,
            "replicas": {"ready": 1},
        }
    )

    with pytest.raises(ArgoRolloutError, match="not Healthy"):
        await svc.verify_rollout_healthy(name="demo", namespace="default")


def test_delete_analysis_template_supports_cluster_and_namespace_scopes():
    svc = _make_service()

    res_ns = svc.delete_analysis_template(name="tpl-ns", namespace="default", scope="namespace")
    assert res_ns["scope"] == "namespace"
    svc._analysis_template_api.delete.assert_called_once_with(name="tpl-ns", namespace="default")

    res_cl = svc.delete_analysis_template(name="tpl-cl", scope="cluster")
    assert res_cl["scope"] == "cluster"
    svc._cluster_analysis_template_api.delete.assert_called_once_with(name="tpl-cl")
