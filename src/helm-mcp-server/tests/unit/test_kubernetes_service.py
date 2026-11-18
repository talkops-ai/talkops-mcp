"""Unit tests for KubernetesService (per-session context isolation, cluster info, discovery prerequisite checks)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from helm_mcp_server.exceptions import KubernetesOperationError
from helm_mcp_server.services.kubernetes_service import KubernetesService


@pytest.mark.asyncio
async def test_get_cluster_info(k8s_service: KubernetesService) -> None:
    """get_cluster_info should return Kubernetes version, node list, and namespace list."""
    info = await k8s_service.get_cluster_info()
    assert info["kubernetes_version"] == "v1.29.2-eks-1234"
    assert info["node_count"] == 2
    assert info["nodes"] == ["node-1", "node-2"]
    assert info["namespace_count"] == 3
    assert info["namespaces"] == ["default", "prod", "argocd"]


@pytest.mark.asyncio
async def test_list_namespaces(k8s_service: KubernetesService) -> None:
    """list_namespaces should return all namespace names."""
    namespaces = await k8s_service.list_namespaces()
    assert namespaces == ["default", "prod", "argocd"]


@pytest.mark.asyncio
async def test_list_contexts(k8s_service: KubernetesService) -> None:
    """list_contexts should format available contexts and highlight current context."""
    ctx_data = await k8s_service.list_contexts()
    assert ctx_data["total_contexts"] == 2
    assert ctx_data["current_context"] == "dev-cluster"
    assert ctx_data["contexts"][0]["name"] == "dev-cluster"
    assert ctx_data["contexts"][0]["is_current"] is True
    assert ctx_data["contexts"][1]["name"] == "prod-cluster"
    assert ctx_data["contexts"][1]["is_current"] is False


@pytest.mark.asyncio
async def test_set_context_per_session_isolation(k8s_service: KubernetesService) -> None:
    """Switching context in session-a must not overwrite explicit context in session-b."""
    res_a = await k8s_service.set_context("prod-cluster", session_id="session-a")
    assert res_a["success"] is True
    assert res_a["context_name"] == "prod-cluster"
    assert res_a["session_id"] == "session-a"

    res_b = await k8s_service.set_context("dev-cluster", session_id="session-b")
    assert res_b["success"] is True
    assert res_b["context_name"] == "dev-cluster"

    assert k8s_service.get_active_context("session-a") == "prod-cluster"
    assert k8s_service.get_active_context("session-b") == "dev-cluster"


@pytest.mark.asyncio
async def test_set_context_invalid_context_raises_model_directed_error(
    k8s_service: KubernetesService,
) -> None:
    """Switching to a non-existent context should raise KubernetesOperationError with available contexts."""
    with pytest.raises(KubernetesOperationError, match="kubernetes://contexts"):
        await k8s_service.set_context("nonexistent-cluster", session_id="session-a")


@pytest.mark.asyncio
async def test_check_prerequisites_semver_and_discovered_resources(
    k8s_service: KubernetesService,
) -> None:
    """check_prerequisites should verify semver and query Kubernetes Discovery APIs for kinds/CRDs."""
    # Case 1: All prerequisites met (Deployment, Service, Certificate CRD exist; v1.29.2 >= 1.25.0)
    ok_res = await k8s_service.check_prerequisites(
        min_kubernetes_version="1.25.0",
        required_api_resources=["Deployment", "Service", "Certificate", "networking.k8s.io/v1"],
    )
    assert ok_res["all_prerequisites_met"] is True
    assert ok_res["api_version_check"]["meets_requirement"] is True
    assert ok_res["resource_check"]["missing"] == []
    assert "Certificate" in ok_res["resource_check"]["available"]

    # Case 2: Missing CRD (ServiceMonitor) and version higher than cluster (1.32.0 > 1.29.2)
    fail_res = await k8s_service.check_prerequisites(
        min_kubernetes_version="1.32.0",
        required_api_resources=["Deployment", "ServiceMonitor"],
    )
    assert fail_res["all_prerequisites_met"] is False
    assert fail_res["api_version_check"]["meets_requirement"] is False
    assert fail_res["resource_check"]["missing"] == ["ServiceMonitor"]
    assert fail_res["resource_check"]["all_available"] is False


@pytest.mark.asyncio
async def test_check_prerequisites_semver_handles_single_digit_minor_version(
    k8s_service: KubernetesService,
    mock_k8s_module: Any,
) -> None:
    """Cluster version v1.9.0 must fail against min_kubernetes_version 1.28.0."""
    mock_k8s_module.version_api.get_code.return_value = SimpleNamespace(git_version="v1.9.0")
    res = await k8s_service.check_prerequisites(min_kubernetes_version="1.28.0")
    assert res["api_version_check"]["meets_requirement"] is False
    assert res["all_prerequisites_met"] is False
