"""Unit tests for MCP_ALLOW_WRITE write guard across ArgoCDService and ArgoCDManagementService."""

import pytest
import respx

from argocd_mcp_server.config import ServerConfig
from argocd_mcp_server.exceptions import ArgoCDOperationError
from argocd_mcp_server.services import (
    ArgoCDClient,
    ArgoCDManagementService,
    ArgoCDService,
)


@pytest.mark.asyncio
async def test_readonly_blocks_all_service_mutations(
    readonly_config: ServerConfig,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """When allow_write=False, all mutating service methods raise ArgoCDOperationError."""
    client = ArgoCDClient(readonly_config)
    app_svc = ArgoCDService(readonly_config, client=client)
    mgmt_svc = ArgoCDManagementService(readonly_config, client=client)

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await app_svc.create_application(
            app_name="new-app",
            project="default",
            repo_url="https://github.com/org/repo.git",
            path="k8s",
            destination_namespace="default",
        )

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await app_svc.update_application(app_name="payments-service", target_revision="v2.0.0")

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await app_svc.delete_application(app_name="payments-service")

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await app_svc.sync_application(app_name="payments-service", dry_run=False)

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await app_svc.rollback_application(app_name="payments-service", dry_run=False)

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await app_svc.cancel_deployment(app_name="payments-service")

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await mgmt_svc.onboard_repository(repo_url="https://github.com/org/repo.git")

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await mgmt_svc.delete_repository(repo_url="https://github.com/org/repo.git")

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await mgmt_svc.create_project(
            project_name="team-a",
            description="Team A",
            source_repos=["*"],
            destinations=[{"server": "https://kubernetes.default.svc", "namespace": "team-a"}],
        )

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await mgmt_svc.update_project(project_name="production", description="Updated")

    with pytest.raises(ArgoCDOperationError, match="MCP_ALLOW_WRITE=false"):
        await mgmt_svc.delete_project(project_name="production")

    await client.aclose()


@pytest.mark.asyncio
async def test_readonly_allows_dry_run_sync_and_rollback_preview(
    readonly_config: ServerConfig,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """When allow_write=False, dry_run=True sync and rollback previews are permitted."""
    client = ArgoCDClient(readonly_config)
    app_svc = ArgoCDService(readonly_config, client=client)

    sync_res = await app_svc.sync_application(app_name="payments-service", dry_run=True)
    assert sync_res["mode"] == "dry_run"

    rb_res = await app_svc.rollback_application(
        app_name="payments-service", history_id=12, dry_run=True
    )
    assert rb_res["mode"] == "dry_run"
    assert rb_res["history_id"] == 12

    await client.aclose()
