"""Unit tests for ArgoRolloutsService dry_run="All" propagation to Kubernetes APIs (T-U5)."""

from unittest.mock import MagicMock
import pytest

from argo_rollout_mcp_server.config import ServerConfig
from argo_rollout_mcp_server.services.argo_rollouts_service import ArgoRolloutsService


def _make_initialized_service() -> ArgoRolloutsService:
    svc = ArgoRolloutsService(ServerConfig())
    svc._initialized = True
    svc._rollout_api = MagicMock()
    svc._analysis_template_api = MagicMock()
    svc._cluster_analysis_template_api = MagicMock()
    svc._experiment_api = MagicMock()
    svc._apps_v1 = MagicMock()
    svc._core_v1 = MagicMock()
    return svc


@pytest.mark.asyncio
async def test_create_rollout_dry_run_passes_all():
    svc = _make_initialized_service()
    res = await svc.create_rollout(
        name="demo",
        namespace="default",
        image="nginx:1.25",
        replicas=2,
        strategy="canary",
        dry_run=True,
    )
    assert res["status"] == "preview"
    assert res["dry_run"] is True
    _, kwargs = svc._rollout_api.create.call_args
    assert kwargs.get("dry_run") == "All"


@pytest.mark.asyncio
async def test_update_rollout_image_dry_run_passes_all():
    svc = _make_initialized_service()
    current = MagicMock()
    current.to_dict.return_value = {
        "spec": {
            "template": {
                "spec": {"containers": [{"name": "demo", "image": "nginx:1.24"}]}
            }
        }
    }
    svc._rollout_api.get.return_value = current

    res = await svc.update_rollout_image(
        name="demo",
        new_image="nginx:1.25",
        namespace="default",
        dry_run=True,
    )
    assert res["status"] == "preview"
    assert res["dry_run"] is True
    _, kwargs = svc._rollout_api.patch.call_args
    assert kwargs.get("dry_run") == "All"


@pytest.mark.asyncio
async def test_set_analysis_template_dry_run_passes_all():
    svc = _make_initialized_service()
    current = MagicMock()
    current.to_dict.return_value = {"spec": {"strategy": {"canary": {"steps": []}}}}
    svc._rollout_api.get.return_value = current

    res = await svc.set_analysis_template(
        rollout_name="demo",
        template_name="demo-analysis",
        namespace="default",
        metrics=[{"name": "error-rate", "provider": {"prometheus": {"query": "1"}}, "successCondition": "result[0] < 1"}],
        scope="namespace",
        dry_run=True,
    )
    assert res["status"] == "preview"
    assert res["dry_run"] is True
    _, create_kwargs = svc._analysis_template_api.create.call_args
    assert create_kwargs.get("dry_run") == "All"
    _, patch_kwargs = svc._rollout_api.patch.call_args
    assert patch_kwargs.get("dry_run") == "All"


@pytest.mark.asyncio
async def test_create_experiment_dry_run_passes_all():
    svc = _make_initialized_service()
    res = await svc.create_experiment(
        name="exp-1",
        namespace="default",
        templates=[{"name": "base", "replicas": 1, "template": {"spec": {"containers": [{"name": "c", "image": "nginx"}]}}}],
        dry_run=True,
    )
    assert res["status"] == "preview"
    assert res["dry_run"] is True
    _, kwargs = svc._experiment_api.create.call_args
    assert kwargs.get("dry_run") == "All"


@pytest.mark.asyncio
async def test_set_traffic_routing_and_update_strategy_dry_run():
    svc = _make_initialized_service()
    current = MagicMock()
    current.to_dict.return_value = {"spec": {"strategy": {"canary": {"steps": []}}}}
    svc._rollout_api.get.return_value = current

    res_tr = await svc.set_traffic_routing(
        name="demo",
        namespace="default",
        traefik_service_name="demo-wrr",
        dry_run=True,
    )
    assert res_tr["status"] == "preview"
    _, tr_kwargs = svc._rollout_api.patch.call_args
    assert tr_kwargs.get("dry_run") == "All"

    res_st = await svc.update_canary_strategy(
        name="demo",
        namespace="default",
        canary_steps=[{"setWeight": 10}, {"pause": {}}],
        dry_run=True,
    )
    assert res_st["status"] == "preview"
    _, st_kwargs = svc._rollout_api.patch.call_args
    assert st_kwargs.get("dry_run") == "All"
