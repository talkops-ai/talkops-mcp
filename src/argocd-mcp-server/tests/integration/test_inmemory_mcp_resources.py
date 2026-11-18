"""Layer 2 In-Memory FastMCP integration tests for all 8 URI-addressed resources."""

import json
from typing import Any

import pytest
import respx
from fastmcp import Client


@pytest.mark.asyncio
async def test_inmemory_resources_discovery_and_reads(
    mcp_server_write: Any,
    standard_argocd_routes: respx.MockRouter,
) -> None:
    """Verify static and templated argocd:// resources via FastMCP Client."""
    async with Client(mcp_server_write) as client:
        resources = await client.list_resources()
        static_uris = {str(r.uri) for r in resources}
        assert {
            "argocd://applications",
            "argocd://clusters",
            "argocd://repositories",
            "argocd://health",
        }.issubset(static_uris)
        assert "argocd://workflow" not in static_uris

        templates = await client.list_resource_templates()
        template_uris = {str(t.uriTemplate) for t in templates}
        assert {
            "argocd://applications/{app_name}",
            "argocd://applications/{app_name}/history",
            "argocd://applications/{app_name}/resource-tree",
            "argocd://projects/{project_name}",
        }.issubset(template_uris)

        # Read static resources
        apps_raw = await client.read_resource("argocd://applications")
        apps_text = getattr(apps_raw[0], "text", "")
        apps_data = json.loads(apps_text)
        assert apps_data["total"] == 3

        clusters_raw = await client.read_resource("argocd://clusters")
        clusters_text = getattr(clusters_raw[0], "text", "")
        clusters_data = json.loads(clusters_text)
        assert clusters_data["total"] == 2
        assert "SECRET_CLUSTER_BEARER_TOKEN_REDACTED" not in clusters_text

        repos_raw = await client.read_resource("argocd://repositories")
        repos_text = getattr(repos_raw[0], "text", "")
        repos_data = json.loads(repos_text)
        assert repos_data["total"] == 2
        assert "SUPER_SECRET_PASSWORD_SHOULD_BE_REDACTED" not in repos_text

        health_raw = await client.read_resource("argocd://health")
        health_data = json.loads(getattr(health_raw[0], "text", ""))
        assert health_data["status"] == "healthy"
        assert health_data["version"] == "v2.13.1+8a2c1e9"

        # Read templated resources
        app_raw = await client.read_resource("argocd://applications/payments-service")
        app_data = json.loads(getattr(app_raw[0], "text", ""))
        assert app_data["name"] == "payments-service"

        hist_raw = await client.read_resource(
            "argocd://applications/payments-service/history"
        )
        hist_data = json.loads(getattr(hist_raw[0], "text", ""))
        assert hist_data["total_deployments"] == 3
        assert hist_data["history"][-1]["id"] == 13

        tree_raw = await client.read_resource(
            "argocd://applications/payments-service/resource-tree"
        )
        tree_data = json.loads(getattr(tree_raw[0], "text", ""))
        assert tree_data["total_nodes"] == 3

        proj_raw = await client.read_resource("argocd://projects/production")
        proj_data = json.loads(getattr(proj_raw[0], "text", ""))
        assert proj_data["name"] == "production"
