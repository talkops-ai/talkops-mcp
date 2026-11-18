"""Helm release inspection resources: revision history, redacted values, and redacted manifests."""

from __future__ import annotations

from typing import Any, Dict

from helm_mcp_server.exceptions import HelmResourceNotFoundError
from helm_mcp_server.resources.base import BaseResource


class HelmResources(BaseResource):
    """URI-addressed resources for deployed Helm release history, values, and manifests."""

    def register(self, mcp_instance: Any) -> None:
        """Register Helm release resources with FastMCP."""

        @mcp_instance.resource(
            "helm://releases/{namespace}/{release_name}/history",
            mime_type="application/json",
        )
        async def get_release_history(namespace: str, release_name: str) -> Dict[str, Any]:
            """Get revision history for a deployed Helm release in a namespace."""
            try:
                revisions = await self.helm_service.get_release_history(
                    release_name=release_name,
                    namespace=namespace,
                )
                return {
                    "release_name": release_name,
                    "namespace": namespace,
                    "revisions": revisions,
                    "count": len(revisions),
                }
            except Exception as exc:
                raise HelmResourceNotFoundError(
                    f"History not found for release '{release_name}' in namespace '{namespace}': {exc}. "
                    f"Call helm_list_releases(namespace='{namespace}') to find valid release names."
                )

        @mcp_instance.resource(
            "helm://releases/{namespace}/{release_name}/values",
            mime_type="application/json",
        )
        async def get_release_values(namespace: str, release_name: str) -> Dict[str, Any]:
            """Get secret-redacted user override values for a deployed Helm release."""
            try:
                values = await self.helm_service.get_release_values(
                    release_name=release_name,
                    namespace=namespace,
                )
                return {
                    "release_name": release_name,
                    "namespace": namespace,
                    "values": values,
                    "secrets_redacted": True,
                }
            except Exception as exc:
                raise HelmResourceNotFoundError(
                    f"Values not found for release '{release_name}' in namespace '{namespace}': {exc}. "
                    f"Call helm_list_releases(namespace='{namespace}') to find valid release names."
                )

        @mcp_instance.resource(
            "helm://releases/{namespace}/{release_name}/manifest",
            mime_type="text/yaml",
        )
        async def get_release_manifest(namespace: str, release_name: str) -> str:
            """Get secret-redacted Kubernetes YAML manifest for a deployed Helm release."""
            try:
                manifest = await self.helm_service.get_release_manifest(
                    release_name=release_name,
                    namespace=namespace,
                )
                if not manifest or not manifest.strip():
                    raise HelmResourceNotFoundError(
                        f"Manifest is empty for release '{release_name}' in namespace '{namespace}'."
                    )
                return manifest
            except HelmResourceNotFoundError:
                raise
            except Exception as exc:
                raise HelmResourceNotFoundError(
                    f"Manifest not found for release '{release_name}' in namespace '{namespace}': {exc}. "
                    f"Call helm_list_releases(namespace='{namespace}') to find valid release names."
                )
