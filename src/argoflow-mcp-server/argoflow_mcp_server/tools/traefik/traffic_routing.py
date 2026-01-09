"""Traefik traffic routing tools - Route management for canary deployments."""

from typing import Dict, Any, Optional, List
from pydantic import Field
from fastmcp import Context

from argoflow_mcp_server.tools.base import BaseTool
from argoflow_mcp_server.exceptions.custom import (
    TraefikOperationError,
    TraefikRouteNotFoundError,
    TraefikServiceError,
    TraefikWeightError,
)


class TrafficRoutingTools(BaseTool):
    """Tools for creating and managing Traefik traffic routes."""
    
    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""
        
        @mcp_instance.tool()
        async def traefik_create_weighted_route(
            route_name: str = Field(..., min_length=1, description='Route name'),
            hostname: str = Field(..., min_length=1, description='Hostname for routing (e.g., api.example.com)'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            stable_service: Optional[str] = Field(default=None, description='Stable service name (default: {route_name}-stable)'),
            canary_service: Optional[str] = Field(default=None, description='Canary service name (default: {route_name}-canary)'),
            stable_weight: int = Field(default=100, ge=0, le=1000, description='Initial weight for stable service'),
            canary_weight: int = Field(default=0, ge=0, le=1000, description='Initial weight for canary service'),
            entry_points: Optional[List[str]] = Field(default=None, description='Entry points (default: ["web"])'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Create weighted route for canary deployment.
            
            Creates a TraefikService with weighted round-robin distribution and
            an IngressRoute pointing to it. This is the foundation for progressive
            traffic shifting in canary deployments.
            
            Args:
                route_name: Name of the route
                hostname: Hostname for routing
                namespace: Kubernetes namespace
                stable_service: Stable service name
                canary_service: Canary service name
                stable_weight: Initial weight for stable (typically 100)
                canary_weight: Initial weight for canary (typically 0)
                entry_points: Traefik entry points
            
            Returns:
                Creation result with route details and initial distribution
            
            Raises:
                TraefikWeightError: If weights are invalid
                TraefikServiceError: If creation fails
            
            Example:
                Start with 100% stable, 0% canary, then progressively shift
            """
            await ctx.info(
                f"Creating weighted route '{route_name}' for hostname '{hostname}'",
                extra={
                    'route_name': route_name,
                    'hostname': hostname,
                    'namespace': namespace,
                    'stable_weight': stable_weight,
                    'canary_weight': canary_weight
                }
            )
            
            try:
                result = await self.traefik_service.create_weighted_route(
                    route_name=route_name,
                    namespace=namespace,
                    hostname=hostname,
                    stable_service=stable_service,
                    canary_service=canary_service,
                    stable_weight=stable_weight,
                    canary_weight=canary_weight,
                    entry_points=entry_points
                )
                
                await ctx.info(
                    f"Successfully created weighted route '{route_name}'",
                    extra={
                        'route_name': route_name,
                        'stable_percent': result.get('stable_percent'),
                        'canary_percent': result.get('canary_percent')
                    }
                )
                
                return result
            
            except TraefikWeightError as e:
                await ctx.error(f"Invalid weight configuration: {str(e)}")
                raise
            except TraefikServiceError as e:
                await ctx.error(f"Failed to create route: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(
                    f"Failed to create weighted route: {str(e)}",
                    extra={'route_name': route_name, 'error': str(e)}
                )
                raise TraefikOperationError(f'Route creation failed: {str(e)}')
        
        @mcp_instance.tool()
        async def traefik_update_route_weights(
            route_name: str = Field(..., min_length=1, description='Route name'),
            stable_weight: int = Field(..., ge=0, le=1000, description='New weight for stable service'),
            canary_weight: int = Field(..., ge=0, le=1000, description='New weight for canary service'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Update traffic weights between stable and canary.
            
            Progressive traffic shift for canary deployment:
            100/0 → 95/5 → 90/10 → 75/25 → 50/50 → 0/100
            
            Args:
                route_name: Name of the route
                stable_weight: New weight for stable service
                canary_weight: New weight for canary service
                namespace: Kubernetes namespace
            
            Returns:
                Update result with calculated percentages
            
            Raises:
                TraefikWeightError: If weights are invalid
                TraefikRouteNotFoundError: If route doesn't exist
            
            Example weights for progressive rollout:
                - 5%:   stable=95, canary=5
                - 10%:  stable=90, canary=10
                - 25%:  stable=75, canary=25
                - 50%:  stable=50, canary=50
                - 100%: stable=0,  canary=100
            """
            total = stable_weight + canary_weight
            stable_pct = (stable_weight / total * 100) if total > 0 else 0
            canary_pct = (canary_weight / total * 100) if total > 0 else 0
            
            await ctx.info(
                f"Updating route '{route_name}' weights: {stable_pct:.1f}% stable, {canary_pct:.1f}% canary",
                extra={
                    'route_name': route_name,
                    'namespace': namespace,
                    'stable_weight': stable_weight,
                    'canary_weight': canary_weight
                }
            )
            
            try:
                result = await self.traefik_service.update_route_weights(
                    route_name=route_name,
                    namespace=namespace,
                    stable_weight=stable_weight,
                    canary_weight=canary_weight
                )
                
                await ctx.info(
                    f"Successfully updated weights for route '{route_name}'",
                    extra={
                        'route_name': route_name,
                        'stable_percent': result.get('stable_percent'),
                        'canary_percent': result.get('canary_percent')
                    }
                )
                
                return result
            
            except TraefikWeightError as e:
                await ctx.error(f"Invalid weight configuration: {str(e)}")
                raise
            except TraefikRouteNotFoundError as e:
                await ctx.error(f"Route not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to update weights: {str(e)}")
                raise TraefikOperationError(f'Weight update failed: {str(e)}')
        
        @mcp_instance.tool()
        async def traefik_delete_route(
            route_name: str = Field(..., min_length=1, description='Route name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Delete weighted route (cleanup after rollout complete).
            
            Removes both the IngressRoute and TraefikService created for
            the canary deployment. Use this after rollout is complete and
            you've fully transitioned to the new version.
            
            Args:
                route_name: Name of the route to delete
                namespace: Kubernetes namespace
            
            Returns:
                Deletion result with list of deleted resources
            
            Raises:
                TraefikRouteNotFoundError: If route doesn't exist
            """
            await ctx.warning(
                f"Deleting route '{route_name}' from namespace '{namespace}'",
                extra={'route_name': route_name, 'namespace': namespace}
            )
            
            try:
                result = await self.traefik_service.delete_route(
                    route_name=route_name,
                    namespace=namespace
                )
                
                await ctx.info(
                    f"Successfully deleted route '{route_name}'",
                    extra={
                        'route_name': route_name,
                        'deleted_resources': result.get('deleted_resources')
                    }
                )
                
                return result
            
            except TraefikRouteNotFoundError as e:
                await ctx.error(f"Route not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to delete route: {str(e)}")
                raise TraefikOperationError(f'Route deletion failed: {str(e)}')
        
        @mcp_instance.tool()
        async def traefik_get_traffic_distribution(
            route_name: str = Field(..., min_length=1, description='Route name'),
            namespace: str = Field(default='default', description='Kubernetes namespace'),
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get current traffic distribution for a route.
            
            Returns the current traffic weight distribution between stable
            and canary services, including calculated percentages.
            
            Args:
                route_name: Name of the route
                namespace: Kubernetes namespace
            
            Returns:
                Traffic distribution with weights and percentages
            
            Raises:
                TraefikRouteNotFoundError: If route doesn't exist
            """
            await ctx.info(
                f"Retrieving traffic distribution for route '{route_name}'",
                extra={'route_name': route_name, 'namespace': namespace}
            )
            
            try:
                result = await self.traefik_service.get_service_traffic_distribution(
                    route_name=route_name,
                    namespace=namespace
                )
                
                distribution = result.get('distribution', [])
                await ctx.info(
                    f"Traffic distribution for '{route_name}': " +
                    ", ".join([f"{d['service']}: {d['percent']:.1f}%" for d in distribution]),
                    extra={'route_name': route_name, 'distribution': distribution}
                )
                
                return result
            
            except TraefikRouteNotFoundError as e:
                await ctx.error(f"Route not found: {str(e)}")
                raise
            except Exception as e:
                await ctx.error(f"Failed to get traffic distribution: {str(e)}")
                raise TraefikOperationError(f'Traffic distribution retrieval failed: {str(e)}')
