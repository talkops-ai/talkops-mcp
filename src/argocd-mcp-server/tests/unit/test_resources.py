"""Unit tests for cluster listing and health check service methods backing MCP resources."""

import pytest
import respx

from argocd_mcp_server.services import ArgoCDService


@pytest.mark.asyncio
async def test_list_clusters_redacts_bearer_token(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """list_clusters returns cluster metadata and redacts secret config tokens."""
    clusters = await argocd_service.list_clusters()
    assert clusters["total"] == 2
    assert clusters["clusters"][0]["name"] == "in-cluster"
    assert clusters["clusters"][0]["server_version"] == "1.31"
    assert "SECRET_CLUSTER_BEARER_TOKEN_REDACTED" not in str(clusters)


@pytest.mark.asyncio
async def test_check_health_reports_version_and_write_posture(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """check_health returns ArgoCD version and server allow_write posture."""
    health = await argocd_service.check_health()
    assert health["status"] == "healthy"
    assert health["version"] == "v2.13.1+8a2c1e9"
    assert health["allow_write"] is True
