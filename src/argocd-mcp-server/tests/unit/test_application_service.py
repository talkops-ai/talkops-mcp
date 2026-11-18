"""Unit tests for ArgoCDService application and deployment methods."""

import httpx
import pytest
import respx

from argocd_mcp_server.exceptions import ApplicationNotFound, ArgoCDOperationError
from argocd_mcp_server.services import ArgoCDService
from tests.conftest import BASE_URL


@pytest.mark.asyncio
async def test_list_applications_filtering_and_pagination(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """list_applications filters by cluster, namespace, project, sync_status, and health_status."""
    all_apps = await argocd_service.list_applications()
    assert all_apps["total"] == 3
    assert len(all_apps["applications"]) == 3

    # Filter by cluster substring
    eks_apps = await argocd_service.list_applications(cluster="eks-prod")
    assert eks_apps["total"] == 1
    assert eks_apps["applications"][0]["name"] == "checkout-worker"

    # Filter by namespace
    ns_apps = await argocd_service.list_applications(namespace="payments-prod")
    assert ns_apps["total"] == 1
    assert ns_apps["applications"][0]["name"] == "payments-service"

    # Filter by sync_status and health_status
    degraded = await argocd_service.list_applications(
        sync_status="OutOfSync", health_status="Degraded"
    )
    assert degraded["total"] == 1
    assert degraded["applications"][0]["name"] == "checkout-worker"

    # Pagination
    paged = await argocd_service.list_applications(limit=1, offset=1)
    assert paged["total"] == 3
    assert len(paged["applications"]) == 1
    assert paged["applications"][0]["name"] == "checkout-worker"


@pytest.mark.asyncio
async def test_get_application_details_real_history_fields(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """get_application_details maps real ArgoCD RevisionHistory fields (id, deployedAt, initiatedBy.username) (Fixes N4)."""
    summary = await argocd_service.get_application_details(
        app_name="payments-service", detail_level="summary"
    )
    assert summary["name"] == "payments-service"
    assert summary["project"] == "production"
    assert summary["auto_sync_enabled"] is False
    assert summary["resource_summary"]["total"] == 3
    assert summary["resource_summary"]["out_of_sync"] == 1

    history = summary["sync_history"]
    assert len(history) == 3
    latest = history[-1]
    assert latest["id"] == 13
    assert latest["revision"] == "8f3c1a9d4e2b"
    assert latest["deployed_at"] == "2026-10-30T15:30:00Z"
    assert latest["initiated_by"] == "ci-bot"


@pytest.mark.asyncio
async def test_get_application_diff_live_vs_target_and_validation(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """get_application_diff compares managed-resources liveState vs targetState and runs dry-run validation (Fixes N3)."""
    diff = await argocd_service.get_application_diff(
        app_name="payments-service", revision="v1.4.0", validate=True
    )
    assert diff["app_name"] == "payments-service"
    assert diff["changes_detected"] is True
    assert diff["diff_count"] == 1
    assert diff["diffs"][0]["kind"] == "Deployment"
    assert diff["diffs"][0]["name"] == "payments-api"
    assert diff["validation"]["checked"] is True
    assert diff["validation"]["valid"] is True


@pytest.mark.asyncio
async def test_get_application_logs_parses_ndjson_stream(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """get_application_logs parses ArgoCD NDJSON log stream lines and detects errors (Fixes N6)."""
    logs = await argocd_service.get_application_logs(
        app_name="payments-service",
        pod_name="payments-api-7f8c9b-abc12",
        errors_only=False,
    )
    assert logs["pods_checked"] == 1
    pod_entry = logs["pod_logs"][0]
    assert pod_entry["line_count"] == 3
    assert pod_entry["error_count"] == 1
    assert "ERROR Failed to connect to upstream ledger" in pod_entry["sample_errors"][0]

    # Filter errors_only=True
    err_only = await argocd_service.get_application_logs(
        app_name="payments-service",
        pod_name="payments-api-7f8c9b-abc12",
        errors_only=True,
    )
    assert err_only["pod_logs"][0]["line_count"] == 1


@pytest.mark.asyncio
async def test_create_update_delete_application(
    argocd_service: ArgoCDService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """create_application, update_application, and delete_application execute against ArgoCD REST API."""
    created = await argocd_service.create_application(
        app_name="payments-service",
        project="production",
        repo_url="https://github.com/org/gitops-manifests.git",
        path="apps/payments/overlays/prod",
        destination_namespace="payments-prod",
        sync_policy={"automated": True, "prune": True, "self_heal": True, "create_namespace": True},
    )
    assert created["created"] is True
    assert created["auto_sync_enabled"] is True

    updated = await argocd_service.update_application(
        app_name="payments-service",
        target_revision="v1.5.0",
        sync_policy={"automated": False},
    )
    assert updated["updated"] is True
    assert "target_revision" in updated["updated_fields"]
    assert updated["auto_sync_enabled"] is False

    deleted = await argocd_service.delete_application(
        app_name="payments-service", cascade=True
    )
    assert deleted["deleted"] is True


@pytest.mark.asyncio
async def test_application_not_found_includes_recovery_guidance(
    argocd_service: ArgoCDService,
    respx_mock: respx.MockRouter,
) -> None:
    """404 on application lookup raises ApplicationNotFound with guidance to call list_applications."""
    respx_mock.get(f"{BASE_URL}/api/v1/applications/missing-app").mock(
        return_value=httpx.Response(404, json={"message": "applications.argoproj.io not found"})
    )
    with pytest.raises(ApplicationNotFound, match="list_applications"):
        await argocd_service.get_application_details(app_name="missing-app")
