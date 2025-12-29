"""Traffic distribution resources.

Provides real-time traffic weight distribution from Traefik routes.
"""

import json
import logging
from typing import List
from mcp.types import Resource, TextContent
from argoflow_mcp_server.resources.base import BaseResource

logger = logging.getLogger(__name__)


class TrafficResources(BaseResource):
    """Traffic distribution resources.
    
    Provides live traffic weights from Traefik.
    Update frequency: Every 5 seconds.
    """
    
    def register(self, mcp_instance) -> None:
        """Register traffic resources with FastMCP.
        
        Args:
            mcp_instance: FastMCP server instance
        """
        
        @mcp_instance.resource("argoflow://traffic/{namespace}/{route_name}/distribution")
        async def traffic_distribution(namespace: str, route_name: str) -> str:
            """Get traffic distribution for a route.
            
            Args:
                namespace: Kubernetes namespace
                route_name: Route name
            
            Returns:
                JSON string with traffic distribution details
            """
            try:
                if not self.traefik_service:
                    return json.dumps({
                        "error": "Traefik service not available",
                        "route": route_name,
                        "namespace": namespace
                    }, indent=2)
                
                # Get traffic distribution from Traefik service
                distribution = await self.traefik_service.get_service_traffic_distribution(
                    route_name=route_name,
                    namespace=namespace
                )
                
                # Parse the distribution data
                services = distribution.get('services', [])
                total_weight = distribution.get('totalWeight', 0)
                
                # Calculate percentages
                weights = []
                for svc in services:
                    weight = svc.get('weight', 0)
                    percentage = (weight / total_weight * 100) if total_weight > 0 else 0
                    
                    weights.append({
                        "service": svc.get('name', 'unknown'),
                        "weight": weight,
                        "percentage": round(percentage, 2)
                    })
                
                resource_data = {
                    "route": route_name,
                    "namespace": namespace,
                    "weights": weights,
                    "totalWeight": total_weight
                }
                
                return json.dumps(resource_data, indent=2)
                
            except Exception as e:
                logger.error(f"Error getting traffic distribution: {e}")
                return json.dumps({
                    "error": str(e),
                    "route": route_name,
                    "namespace": namespace
                }, indent=2)
        
        @mcp_instance.resource("argoflow://traffic/routes/list")
        async def list_traffic_routes() -> List[Resource]:
            """List all Traefik routes with traffic distribution.
            
            Returns:
                List of traffic route resources
            """
            try:
                if not self.traefik_service:
                    logger.warning("Traefik service not available")
                    return []
                
                # Get namespace from config
                namespace = getattr(self.config, 'namespace', 'default') if self.config else 'default'
                
                # List TraefikService resources (weighted routes)
                # Note: This requires listing CRDs, implementing simplified version
                # In production, you'd query the Kubernetes API for TraefikService CRDs
                
                # For now, return empty list with a note
                # This can be enhanced to actually query Traefik CRDs
                resources = []
                
                # Placeholder for when Traefik route listing is implemented
                logger.info("TraefikService listing not yet implemented")
                
                return resources
                
            except Exception as e:
                logger.error(f"Error listing traffic routes: {e}")
                return []
