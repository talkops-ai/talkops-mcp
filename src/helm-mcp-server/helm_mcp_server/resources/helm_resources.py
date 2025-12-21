"""Helm-related resources."""

import json
from typing import List, Optional
from mcp.types import Resource, TextContent
from helm_mcp_server.exceptions import HelmResourceError, HelmResourceNotFoundError
from helm_mcp_server.resources.base import BaseResource


class HelmResources(BaseResource):
    """Helm release resources."""
    
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP."""
        
        @mcp_instance.resource("helm://releases")
        async def list_helm_releases() -> List[Resource]:
            """List all Helm releases in cluster.
            
            Returns dynamic resources for each release.
            """
            try:
                # Get releases from Kubernetes service
                releases = await self.k8s_service.get_helm_releases()
                
                return [
                    Resource(
                        uri=f"helm://releases/{rel['name']}",
                        name=f"Release: {rel['name']}",
                        description=f"Helm release {rel['name']} in namespace {rel.get('namespace', 'default')}",
                        mimeType="application/json",
                        contents=[
                            TextContent(
                                text=json.dumps(rel, indent=2),
                                mimeType="application/json"
                            )
                        ]
                    )
                    for rel in releases
                ]
            except Exception as e:
                # Return empty list on error (graceful degradation)
                return []
        
        @mcp_instance.resource(
            "helm://releases/{release_name}",
            mime_type="application/json"
        )
        async def get_release_details(release_name: str) -> dict:
            """Get detailed information about a specific Helm release.
            
            Args:
                release_name: Name of the Helm release
            
            Returns:
                Dictionary with release details
            
            Raises:
                HelmResourceNotFoundError: If release not found
            """
            try:
                # First, find the release across all namespaces
                all_releases = await self.k8s_service.get_helm_releases()
                
                # Find the release by name
                release = None
                for rel in all_releases:
                    if rel.get('name') == release_name:
                        release = rel
                        break
                
                if not release:
                    raise HelmResourceNotFoundError(f"Release not found: {release_name}")
                
                # Get detailed status from Helm service
                namespace = release.get('namespace', 'default')
                release_info = await self.helm_service.get_release_status(
                    release_name=release_name,
                    namespace=namespace
                )
                
                # Return dict directly - FastMCP will convert to JSON automatically
                return release_info
            except HelmResourceNotFoundError:
                raise
            except Exception as e:
                raise HelmResourceNotFoundError(f"Release not found: {release_name}")

