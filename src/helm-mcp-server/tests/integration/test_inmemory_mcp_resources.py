"""In-memory FastMCP integration tests for all 10 URI-addressed MCP resources."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml
from fastmcp import Client

from helm_mcp_server.utils.helm_helper import REDACTED_PLACEHOLDER
from tests.conftest import get_text


@pytest.mark.asyncio
async def test_static_and_template_resources_registration(bootstrapped_mcp: Any) -> None:
    """Verify static resources and URI resource templates are registered on the FastMCP server."""
    async with Client(bootstrapped_mcp) as client:
        resources = await client.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        assert {
            "helm://repositories",
            "kubernetes://cluster-info",
            "kubernetes://namespaces",
            "kubernetes://contexts",
        }.issubset(resource_uris)

        templates = await client.list_resource_templates()
        template_uris = {str(t.uriTemplate) for t in templates}
        assert {
            "helm://charts/{repository}/{chart_name}",
            "helm://charts/{repository}/{chart_name}/values",
            "helm://charts/{repository}/{chart_name}/readme",
            "helm://releases/{namespace}/{release_name}/history",
            "helm://releases/{namespace}/{release_name}/values",
            "helm://releases/{namespace}/{release_name}/manifest",
        }.issubset(template_uris)


@pytest.mark.asyncio
async def test_read_all_10_mcp_resources_via_client(bootstrapped_mcp: Any) -> None:
    """Read all 10 URI-addressed resources via Client.read_resource and verify structured payloads and redaction."""
    async with Client(bootstrapped_mcp) as client:
        # 1. helm://repositories
        repos_res = await client.read_resource("helm://repositories")
        repos_data = json.loads(get_text(repos_res))
        assert repos_data["count"] == 2
        assert repos_data["repositories"][0]["name"] == "bitnami"

        # 2. helm://charts/bitnami/postgresql
        chart_res = await client.read_resource("helm://charts/bitnami/postgresql")
        chart_data = json.loads(get_text(chart_res))
        assert chart_data["name"] == "postgresql"
        assert chart_data["version"] == "15.5.0"

        # 3. helm://charts/bitnami/postgresql/values
        cval_res = await client.read_resource("helm://charts/bitnami/postgresql/values")
        cval_data = yaml.safe_load(get_text(cval_res))
        assert "auth" in cval_data

        # 4. helm://charts/bitnami/postgresql/readme
        readme_res = await client.read_resource("helm://charts/bitnami/postgresql/readme")
        readme_text = get_text(readme_res)
        assert "# Bitnami PostgreSQL" in readme_text

        # 5. helm://releases/prod/my-postgres/history
        hist_res = await client.read_resource("helm://releases/prod/my-postgres/history")
        hist_data = json.loads(get_text(hist_res))
        assert hist_data["release_name"] == "my-postgres"
        assert hist_data["count"] == 2

        # 6. helm://releases/prod/my-postgres/values (must redact passwords)
        rval_res = await client.read_resource("helm://releases/prod/my-postgres/values")
        rval_data = json.loads(get_text(rval_res))
        assert rval_data["values"]["auth"]["postgresPassword"] == REDACTED_PLACEHOLDER
        assert rval_data["values"]["auth"]["existingSecret"] == "prod-postgres-secret"

        # 7. helm://releases/prod/my-postgres/manifest (must redact Secret data)
        rman_res = await client.read_resource("helm://releases/prod/my-postgres/manifest")
        rman_text = get_text(rman_res)
        assert REDACTED_PLACEHOLDER in rman_text
        assert "c2VjcmV0MTIz" not in rman_text

        # 8. kubernetes://cluster-info
        cluster_res = await client.read_resource("kubernetes://cluster-info")
        cluster_data = json.loads(get_text(cluster_res))
        assert cluster_data["kubernetes_version"] == "v1.29.2-eks-1234"
        assert cluster_data["node_count"] == 2

        # 9. kubernetes://namespaces
        ns_res = await client.read_resource("kubernetes://namespaces")
        ns_data = json.loads(get_text(ns_res))
        assert ns_data["namespaces"] == ["default", "prod", "argocd"]

        # 10. kubernetes://contexts
        ctx_res = await client.read_resource("kubernetes://contexts")
        ctx_data = json.loads(get_text(ctx_res))
        assert ctx_data["total_contexts"] == 2
        assert ctx_data["current_context"] == "dev-cluster"
