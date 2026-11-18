"""Layer 3 E2E workflow test for onboarding a repository, creating an AppProject, and registering an application."""

import json
from typing import Any, Dict

import pytest
import respx
from fastmcp import Client


def _extract_data(result: Any) -> Dict[str, Any]:
    if getattr(result, "data", None) is not None and isinstance(result.data, dict):
        return result.data
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_e2e_repository_and_project_onboarding_workflow(
    mcp_server_write: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """Execute Validate Repo -> Onboard Repo -> Create Project -> Create Application -> Dry-Run Sync."""
    repo_url = "https://github.com/org/gitops-manifests.git"

    async with Client(mcp_server_write) as client:
        # Step 1: Validate repository connectivity (zero secrets in arguments)
        val = _extract_data(
            await client.call_tool(
                "validate_repository_connection",
                {"repo_url": repo_url, "insecure": False},
            )
        )
        assert val["valid"] is True
        assert val["auth_mode"] == "https"

        # Step 2: Onboard repository
        onboard = _extract_data(
            await client.call_tool(
                "onboard_repository",
                {
                    "repo_url": repo_url,
                    "repo_type": "git",
                    "project": "production",
                },
            )
        )
        assert onboard["created"] is True
        assert onboard["connection_status"] == "Successful"

        # Step 3: Create AppProject with RBAC restrictions
        proj = _extract_data(
            await client.call_tool(
                "create_project",
                {
                    "project_name": "production",
                    "description": "Production workloads",
                    "source_repos": [repo_url],
                    "destinations": [
                        {
                            "server": "https://kubernetes.default.svc",
                            "namespace": "payments-prod",
                        }
                    ],
                    "resource_restrictions": {
                        "cluster_resource_whitelist": [{"group": "", "kind": "Namespace"}]
                    },
                },
            )
        )
        assert proj["created"] is True
        assert "raw_response" not in proj

        # Step 4: Create Application in the project
        app = _extract_data(
            await client.call_tool(
                "create_application",
                {
                    "app_name": "payments-service",
                    "project": "production",
                    "repo_url": repo_url,
                    "path": "apps/payments/overlays/prod",
                    "destination_namespace": "payments-prod",
                    "target_revision": "v1.4.0",
                },
            )
        )
        assert app["created"] is True

        # Step 5: Preview initial sync via dry_run=True
        sync_preview = _extract_data(
            await client.call_tool(
                "sync_application",
                {"app_name": "payments-service", "dry_run": True},
            )
        )
        assert sync_preview["mode"] == "dry_run"
