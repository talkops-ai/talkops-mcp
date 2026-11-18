"""Regression unit tests for bugs caught during live Domain 3 natural-language evals."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from argo_rollout_mcp_server.resources.metrics_resources import _query_prometheus
from argo_rollout_mcp_server.services.argo_rollouts_service import ArgoRolloutsService
from argo_rollout_mcp_server.services.generator_service import GeneratorService
from argo_rollout_mcp_server.config import ServerConfig


def test_query_prometheus_handles_scalar_and_vector():
    """_probe_prometheus sends query=1 which returns resultType='scalar' ([ts, '1'])."""
    scalar_resp = MagicMock()
    scalar_resp.raise_for_status = MagicMock()
    scalar_resp.json.return_value = {
        "status": "success",
        "data": {"resultType": "scalar", "result": [1731670000.0, "1"]},
    }

    vector_resp = MagicMock()
    vector_resp.raise_for_status = MagicMock()
    vector_resp.json.return_value = {
        "status": "success",
        "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1731670000.0, "0.002"]}]},
    }

    with patch("requests.get", side_effect=[scalar_resp, vector_resp]):
        assert _query_prometheus("http://localhost:19090", "1") == pytest.approx(1.0)
        assert _query_prometheus("http://localhost:19090", "rate(x[1m])") == pytest.approx(0.002)


@pytest.mark.asyncio
async def test_convert_rollout_to_deployment_live_accepts_dict_manifest():
    """get_rollout_manifest() returns a dict; convert_rollout_to_deployment_live must not crash with dict.read."""
    cfg = ServerConfig()
    svc = ArgoRolloutsService(cfg)
    gen = GeneratorService(cfg)
    svc.get_rollout_manifest = AsyncMock(
        return_value={
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Rollout",
            "metadata": {"name": "quote", "namespace": "otel-demo-rev"},
            "spec": {
                "replicas": 2,
                "selector": {"matchLabels": {"app": "quote"}},
                "template": {
                    "metadata": {"labels": {"app": "quote"}},
                    "spec": {"containers": [{"name": "quote", "image": "ghcr.io/open-telemetry/demo:2.2.0-quote"}]},
                },
                "strategy": {"canary": {"steps": [{"setWeight": 25}]}},
            },
        }
    )

    res = await svc.convert_rollout_to_deployment_live(
        name="quote",
        namespace="otel-demo-rev",
        deployment_strategy="RollingUpdate",
        dry_run=True,
        generator_service=gen,
    )
    assert res["status"] == "preview"
    assert "kind: Deployment" in res["manifest"]
    assert "quote" in res["manifest"]


def test_generator_service_ensure_k8s_client_loads_kubeconfig():
    """GeneratorService._ensure_k8s_client must load kubeconfig before AppsV1Api() so host is not localhost:80."""
    cfg = ServerConfig()
    gen = GeneratorService(cfg)
    with patch.object(gen, "_load_kube_config") as mock_load, patch("kubernetes.client.AppsV1Api") as mock_apps:
        gen._ensure_k8s_client()
        mock_load.assert_called_once()
        mock_apps.assert_called_once()


@pytest.mark.asyncio
async def test_create_rollout_rolling_strategy_emits_zero_step_canary():
    """Argo Rollouts CRD has no spec.strategy.rolling field; rolling must emit canary.steps=[]."""
    cfg = ServerConfig()
    svc = ArgoRolloutsService(cfg)
    svc._initialized = True
    svc._rollout_api = MagicMock()
    svc._rollout_api.create.return_value = MagicMock()

    res = await svc.create_rollout(
        name="image-provider",
        namespace="otel-demo-canary",
        image="nginx:1.27-alpine",
        replicas=2,
        strategy="rolling",
        dry_run=True,
    )
    assert "canary:" in res["manifest"]
    assert "steps: []" in res["manifest"]
    assert "rolling:" not in res["manifest"]

