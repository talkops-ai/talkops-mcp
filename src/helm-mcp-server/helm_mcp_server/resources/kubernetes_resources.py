"""Kubernetes-related resources."""

import json
from typing import List
from mcp.types import Resource, TextContent
from helm_mcp_server.exceptions import HelmResourceError
from helm_mcp_server.resources.base import BaseResource


class KubernetesResources(BaseResource):
    """Kubernetes cluster resources."""
    
    def register(self, mcp_instance) -> None:
        """Register resources with FastMCP."""
        
        @mcp_instance.resource(
            "kubernetes://cluster-info",
            mime_type="application/json"
        )
        async def get_cluster_info() -> dict:
            """Get Kubernetes cluster information.
            
            Returns:
                Dictionary with cluster information
            """
            try:
                cluster_info = await self.k8s_service.get_cluster_info()
                
                # Return dict directly - FastMCP will convert to JSON automatically
                return cluster_info
            except Exception as e:
                raise HelmResourceError(f"Failed to get cluster info: {str(e)}")
        
        @mcp_instance.resource("kubernetes://namespaces")
        async def list_namespaces() -> List[Resource]:
            """List all Kubernetes namespaces.
            
            Returns:
                List of namespace resources
            """
            try:
                namespaces = await self.k8s_service.list_namespaces()
                
                return [
                    Resource(
                        uri=f"kubernetes://namespaces/{ns}",
                        name=f"Namespace: {ns}",
                        description=f"Kubernetes namespace {ns}",
                        mimeType="application/json",
                        contents=[
                            TextContent(
                                text=json.dumps({"name": ns}, indent=2),
                                mimeType="application/json"
                            )
                        ]
                    )
                    for ns in namespaces
                ]
            except Exception as e:
                # Return empty list on error
                return []

