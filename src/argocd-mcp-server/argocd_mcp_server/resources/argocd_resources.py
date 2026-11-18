"""ArgoCD MCP URI-addressed read-only resources."""

import json
from typing import Any

from argocd_mcp_server.resources.base import BaseResource


class ArgoCDResources(BaseResource):
    """Read-only URI resources backed by ArgoCDService and ArgoCDManagementService."""

    def register(self, mcp_instance: Any) -> None:
        """Register all 8 URI-addressed resources with FastMCP."""

        @mcp_instance.resource("argocd://applications", mime_type="application/json")
        async def applications() -> str:
            """Catalog of all ArgoCD applications with sync and health status."""
            data = await self.argocd_service.list_applications(limit=200)
            return json.dumps(data, indent=2)

        @mcp_instance.resource("argocd://applications/{app_name}", mime_type="application/json")
        async def application_by_name(app_name: str) -> str:
            """Full state, managed resources, and deployment history for a specific application."""
            data = await self.argocd_service.get_application_details(
                app_name=app_name, detail_level="full"
            )
            return json.dumps(data, indent=2)

        @mcp_instance.resource(
            "argocd://applications/{app_name}/history", mime_type="application/json"
        )
        async def application_history(app_name: str) -> str:
            """Deployment revision history with integer history IDs for rollback targeting."""
            data = await self.argocd_service.get_application_history(app_name=app_name)
            return json.dumps(data, indent=2)

        @mcp_instance.resource(
            "argocd://applications/{app_name}/resource-tree", mime_type="application/json"
        )
        async def application_resource_tree(app_name: str) -> str:
            """Hierarchical Kubernetes resource tree for an application."""
            data = await self.argocd_service.get_application_resource_tree(app_name=app_name)
            return json.dumps(data, indent=2)

        @mcp_instance.resource("argocd://clusters", mime_type="application/json")
        async def clusters() -> str:
            """Registered target Kubernetes clusters with connection state and server version."""
            data = await self.argocd_service.list_clusters()
            return json.dumps(data, indent=2)

        @mcp_instance.resource("argocd://repositories", mime_type="application/json")
        async def repositories() -> str:
            """Onboarded Git, Helm, and OCI repositories (credentials redacted)."""
            data = await self.mgmt_service.list_repositories()
            return json.dumps(data, indent=2)

        @mcp_instance.resource(
            "argocd://projects/{project_name}", mime_type="application/json"
        )
        async def project_by_name(project_name: str) -> str:
            """AppProject RBAC rules, allowed source repositories, and cluster destinations."""
            data = await self.mgmt_service.get_project(project_name=project_name)
            return json.dumps(data, indent=2)

        @mcp_instance.resource("argocd://health", mime_type="application/json")
        async def health() -> str:
            """ArgoCD API connectivity, server version, and MCP guardrail posture."""
            data = await self.argocd_service.check_health()
            return json.dumps(data, indent=2)
