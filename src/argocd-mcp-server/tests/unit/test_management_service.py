"""Unit tests for ArgoCDManagementService repository and project operations (Fixes N5 and N8)."""

import httpx
import pytest
import respx

from argocd_mcp_server.exceptions import ArgoCDOperationError
from argocd_mcp_server.services import ArgoCDManagementService
from tests.conftest import BASE_URL


@pytest.mark.asyncio
async def test_infer_url_scheme_and_server_credential_resolution(
    mgmt_service: ArgoCDManagementService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """onboard_repository infers HTTPS vs SSH from URL and uses server-side credentials."""
    assert mgmt_service.infer_url_scheme("https://github.com/org/repo.git") == "https"
    assert mgmt_service.infer_url_scheme("git@github.com:org/repo.git") == "ssh"
    assert mgmt_service.infer_url_scheme("ssh://git@github.com/org/repo.git") == "ssh"

    with pytest.raises(ValueError, match="Unsupported repository URL format"):
        mgmt_service.infer_url_scheme("ftp://example.com/repo.git")

    https_res = await mgmt_service.onboard_repository(
        repo_url="https://github.com/org/gitops-manifests.git",
        repo_type="git",
        project="production",
    )
    assert https_res["created"] is True
    assert https_res["auth_mode"] == "https"
    assert "password" not in str(https_res)

    ssh_res = await mgmt_service.onboard_repository(
        repo_url="git@github.com:org/private-infra.git",
        repo_type="git",
        project="infra",
    )
    assert ssh_res["created"] is True
    assert ssh_res["auth_mode"] == "ssh"
    assert "PRIVATE KEY" not in str(ssh_res)


@pytest.mark.asyncio
async def test_list_and_get_repositories_redact_credentials(
    mgmt_service: ArgoCDManagementService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """list_repositories and get_repository never include password or sshPrivateKey in output."""
    repos = await mgmt_service.list_repositories()
    assert repos["total"] == 2
    serialized = str(repos)
    assert "SUPER_SECRET_PASSWORD_SHOULD_BE_REDACTED" not in serialized
    assert "BEGIN OPENSSH PRIVATE KEY" not in serialized

    single = await mgmt_service.get_repository(
        repo_url="https://github.com/org/gitops-manifests.git"
    )
    assert single["connection_status"] == "Successful"
    assert "SUPER_SECRET_PASSWORD_SHOULD_BE_REDACTED" not in str(single)


@pytest.mark.asyncio
async def test_project_crud_does_not_leak_raw_response(
    mgmt_service: ArgoCDManagementService,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """create_project, get_project, and update_project omit raw_response (Fixes N5)."""
    created = await mgmt_service.create_project(
        project_name="production",
        description="Production workloads",
        source_repos=["https://github.com/org/gitops-manifests.git"],
        destinations=[{"server": "https://kubernetes.default.svc", "namespace": "payments-prod"}],
        resource_restrictions={
            "cluster_resource_whitelist": [{"group": "", "kind": "Namespace"}],
            "orphaned_resources_warn": True,
        },
    )
    assert created["created"] is True
    assert "raw_response" not in created

    proj = await mgmt_service.get_project("production")
    assert proj["name"] == "production"
    assert "raw_response" not in proj
    assert proj["cluster_resource_whitelist"] == [{"group": "", "kind": "Namespace"}]

    updated = await mgmt_service.update_project(
        project_name="production",
        description="Updated description",
        resource_restrictions={"orphaned_resources_warn": False},
    )
    assert updated["updated"] is True
    assert "raw_response" not in updated


@pytest.mark.asyncio
async def test_delete_default_project_blocked(
    mgmt_service: ArgoCDManagementService,
) -> None:
    """Deleting the built-in 'default' project is rejected."""
    with pytest.raises(ArgoCDOperationError, match="'default' ArgoCD project cannot be deleted"):
        await mgmt_service.delete_project("default")
