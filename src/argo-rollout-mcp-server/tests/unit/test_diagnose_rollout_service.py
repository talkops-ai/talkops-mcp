"""Unit tests for single-call diagnose_rollout diagnosis code classification (T-U7)."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from argo_rollout_mcp_server.config import ServerConfig
from argo_rollout_mcp_server.services.argo_rollouts_service import ArgoRolloutsService


def _make_service() -> ArgoRolloutsService:
    svc = ArgoRolloutsService(ServerConfig())
    svc._initialized = True
    svc._rollout_api = MagicMock()
    svc._core_v1 = MagicMock()
    svc._analysis_run_api = MagicMock()
    return svc


@pytest.mark.asyncio
async def test_diagnose_detects_invalid_spec_and_argocd_drift():
    svc = _make_service()
    svc.list_analysis_runs = AsyncMock(return_value={"analysis_runs": []})

    rollout = MagicMock()
    rollout.to_dict.return_value = {
        "metadata": {
            "name": "demo",
            "namespace": "default",
            "annotations": {"argocd.argoproj.io/tracking-id": "demo"},
        },
        "spec": {
            "replicas": 3,
            "strategy": {
                "canary": {"trafficRouting": {"traefik": {"weightedTraefikServiceName": "wrr"}}},
                "blueGreen": {"activeService": "demo-active"},
            },
        },
        "status": {
            "phase": "Degraded",
            "message": "InvalidSpec: both canary and blueGreen specified",
            "conditions": [{"type": "InvalidSpec", "status": "True", "reason": "InvalidSpec", "message": "conflict"}],
        },
    }
    svc._rollout_api.get.return_value = rollout

    report = await svc.diagnose_rollout(name="demo", namespace="default")
    assert "INVALID_SPEC_STRATEGY_CONFLICT" in report["diagnosis_codes"]
    assert "ARGOCD_TRAFFIC_ROUTING_DRIFT" in report["diagnosis_codes"]


@pytest.mark.asyncio
async def test_diagnose_detects_failed_analysis_and_aborted():
    svc = _make_service()
    svc.list_analysis_runs = AsyncMock(
        return_value={
            "analysis_runs": [
                {
                    "name": "demo-run-1",
                    "phase": "Failed",
                    "failing_metrics": [{"metric": "error-rate", "phase": "Failed", "value": "0.18", "message": ""}],
                }
            ]
        }
    )

    rollout = MagicMock()
    rollout.to_dict.return_value = {
        "metadata": {"name": "demo", "namespace": "default"},
        "spec": {"replicas": 3, "strategy": {"canary": {}}},
        "status": {
            "phase": "Degraded",
            "abort": True,
            "conditions": [{"type": "Progressing", "status": "False", "reason": "RolloutAborted", "message": "aborted"}],
        },
    }
    svc._rollout_api.get.return_value = rollout

    report = await svc.diagnose_rollout(name="demo", namespace="default")
    assert "ANALYSIS_RUN_FAILED" in report["diagnosis_codes"]
    assert "ROLLOUT_ABORTED" in report["diagnosis_codes"]
    assert len(report["failing_metrics"]) == 1


@pytest.mark.asyncio
async def test_diagnose_detects_image_pull_and_crash_loop_backoff():
    svc = _make_service()
    svc.list_analysis_runs = AsyncMock(return_value={"analysis_runs": []})

    rollout = MagicMock()
    rollout.to_dict.return_value = {
        "metadata": {"name": "demo", "namespace": "default"},
        "spec": {"replicas": 2, "selector": {"matchLabels": {"app": "demo"}}, "strategy": {"canary": {}}},
        "status": {"phase": "Progressing", "conditions": []},
    }
    svc._rollout_api.get.return_value = rollout

    pod1 = MagicMock()
    pod1.to_dict.return_value = {
        "metadata": {"name": "demo-pod-1"},
        "status": {
            "phase": "Pending",
            "containerStatuses": [
                {"restartCount": 0, "state": {"waiting": {"reason": "ImagePullBackOff"}}}
            ],
        },
    }
    pod2 = MagicMock()
    pod2.to_dict.return_value = {
        "metadata": {"name": "demo-pod-2"},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {"restartCount": 5, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}
            ],
        },
    }
    svc._core_v1.list_namespaced_pod.return_value = MagicMock(items=[pod1, pod2])
    svc._core_v1.list_namespaced_event.return_value = MagicMock(items=[])

    report = await svc.diagnose_rollout(name="demo", namespace="default", include_pods=True)
    assert "IMAGE_PULL_BACKOFF" in report["diagnosis_codes"]
    assert "CRASH_LOOP_BACKOFF" in report["diagnosis_codes"]
    assert len(report["pods"]) == 2
