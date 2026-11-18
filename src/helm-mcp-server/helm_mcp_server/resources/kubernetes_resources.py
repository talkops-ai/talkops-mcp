"""Kubernetes cluster state and kubeconfig context resources."""

from __future__ import annotations

from typing import Any, Dict

from helm_mcp_server.exceptions import HelmResourceError
from helm_mcp_server.resources.base import BaseResource


class KubernetesResources(BaseResource):
    """URI-addressed resources for cluster info, namespaces, and kubeconfig contexts."""

    def register(self, mcp_instance: Any) -> None:
        """Register Kubernetes resources with FastMCP."""

        @mcp_instance.resource(
            "kubernetes://cluster-info",
            mime_type="application/json",
        )
        async def get_cluster_info() -> Dict[str, Any]:
            """Get Kubernetes cluster version, node summary, namespace summary, and active context."""
            try:
                return await self.k8s_service.get_cluster_info()
            except Exception as exc:
                raise HelmResourceError(
                    f"Failed to get Kubernetes cluster info: {exc}. "
                    "Read 'kubernetes://contexts' or call 'kubernetes_set_context' to select a valid cluster."
                )

        @mcp_instance.resource(
            "kubernetes://namespaces",
            mime_type="application/json",
        )
        async def list_namespaces() -> Dict[str, Any]:
            """List all Kubernetes namespace names in the active cluster."""
            try:
                namespaces = await self.k8s_service.list_namespaces()
                return {
                    "namespaces": namespaces,
                    "count": len(namespaces),
                }
            except Exception as exc:
                raise HelmResourceError(
                    f"Failed to list Kubernetes namespaces: {exc}. "
                    "Verify cluster connectivity via 'kubernetes://cluster-info'."
                )

        @mcp_instance.resource(
            "kubernetes://contexts",
            mime_type="application/json",
        )
        async def list_contexts() -> Dict[str, Any]:
            """List all available Kubernetes contexts from kubeconfig and the active session context."""
            try:
                return await self.k8s_service.list_contexts()
            except Exception as exc:
                raise HelmResourceError(
                    f"Failed to list Kubernetes contexts from kubeconfig: {exc}."
                )
