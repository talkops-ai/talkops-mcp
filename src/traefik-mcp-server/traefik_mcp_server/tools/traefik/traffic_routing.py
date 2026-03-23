"""Traefik traffic routing tools - Route management for canary deployments."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import Field
from fastmcp import Context

from traefik_mcp_server.tools.base import BaseTool
from traefik_mcp_server.exceptions.custom import (
    TraefikOperationError,
    TraefikRouteConfigError,
    TraefikRouteNotFoundError,
    TraefikServiceError,
    TraefikWeightError,
)


class TrafficRoutingTools(BaseTool):
    """Tools for creating and managing Traefik traffic routes."""

    def register(self, mcp_instance) -> None:
        """Register tools with FastMCP."""

        @mcp_instance.tool()
        async def traefik_manage_weighted_routing(
            route_name: str = Field(..., min_length=1, description="Route name"),
            action: Literal["create", "update", "delete", "ensure_backend"] = Field(
                ..., description="create | update | delete | ensure_backend"
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            hostname: Optional[str] = Field(default=None, description="Hostname. Required for create."),
            stable_weight: Optional[int] = Field(default=None, ge=0, le=1000, description="Stable weight. create/update."),
            canary_weight: Optional[int] = Field(default=None, ge=0, le=1000, description="Canary weight. create/update."),
            clean_all: bool = Field(default=False, description="Delete middlewares/backends too. delete only."),
            stable_service: Optional[str] = Field(default=None, description="K8s Service name (stable). create/ensure_backend."),
            canary_service: Optional[str] = Field(default=None, description="K8s Service name (canary). When canary_weight>0."),
            entry_points: Optional[List[str]] = Field(default=None, description='["web"] or ["websecure"]. create only.'),
            path_prefix: Optional[str] = Field(default=None, description="Path match. create only."),
            path_match_type: Literal["PathPrefix", "Path", "PathRegexp"] = Field(default="PathPrefix", description="Path match type. create only."),
            tls_enabled: bool = Field(default=False, description="TLS. create only."),
            tls_secret_name: Optional[str] = Field(default=None, description="TLS secret. create only."),
            middlewares: Optional[List[str]] = Field(default=None, description="Middleware names. create only."),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Weighted canary routing: create (route+TraefikService), update weights, delete, or ensure_backend."""
            assert self.traefik_service is not None
            assert ctx is not None

            # Required params per action
            required = {
                "create": ["hostname", "stable_service", "stable_weight", "canary_weight"],
                "ensure_backend": ["stable_service", "stable_weight", "canary_weight"],
                "update": ["stable_weight", "canary_weight"],
                "delete": [],
            }.get(action, [])
            def _ok(val):
                if val is None:
                    return False
                if isinstance(val, str):
                    return bool(val.strip())
                return True
            params = {"hostname": hostname, "stable_service": stable_service, "stable_weight": stable_weight, "canary_weight": canary_weight}
            missing = [k for k in required if not _ok(params.get(k))]
            if missing:
                raise ValueError(f"Missing for action={action}: {', '.join(missing)}")

            if action == "create":
                try:
                    return await self.traefik_service.create_weighted_route(
                        route_name=route_name,
                        namespace=namespace,
                        hostname=hostname,
                        stable_service=stable_service,
                        canary_service=canary_service,
                        stable_weight=stable_weight,
                        canary_weight=canary_weight,
                        entry_points=entry_points,
                        path_prefix=path_prefix,
                        path_match_type=path_match_type,
                        tls_enabled=tls_enabled,
                        tls_secret_name=tls_secret_name,
                        middlewares=middlewares,
                    )
                except (TraefikWeightError, TraefikRouteConfigError, TraefikServiceError):
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"Route creation failed: {str(e)}")

            if action == "ensure_backend":
                try:
                    return await self.traefik_service.create_traefik_service_only(
                        route_name=route_name,
                        namespace=namespace,
                        stable_service=stable_service,
                        canary_service=canary_service,
                        stable_weight=stable_weight,
                        canary_weight=canary_weight,
                    )
                except (TraefikRouteConfigError, TraefikWeightError, TraefikServiceError):
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"Ensure backend failed: {str(e)}")

            if action == "update":
                try:
                    return await self.traefik_service.update_route_weights(
                        route_name=route_name,
                        namespace=namespace,
                        stable_weight=stable_weight,
                        canary_weight=canary_weight,
                    )
                except (TraefikWeightError, TraefikRouteNotFoundError):
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"Weight update failed: {str(e)}")

            # delete
            try:
                return await self.traefik_service.delete_route(
                    route_name=route_name,
                    namespace=namespace,
                    clean_all=clean_all,
                )
            except TraefikRouteNotFoundError:
                raise
            except Exception as e:
                raise TraefikOperationError(f"Route deletion failed: {str(e)}")

        @mcp_instance.tool()
        async def traefik_manage_simple_route(
            action: Literal["create", "delete"] = Field(
                ...,
                description="create: upsert IngressRoute with direct K8s Service refs | delete: remove that IngressRoute",
            ),
            route_name: str = Field(..., min_length=1, description="IngressRoute name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            routes: Optional[List[Dict[str, Any]]] = Field(
                default=None,
                description='create only: rules with match, service_name, optional service_port, optional middlewares',
            ),
            entry_points: Optional[List[str]] = Field(
                default=None,
                description='create only: e.g. ["web"] or ["websecure"]. Default ["web"].',
            ),
            tls_enabled: bool = Field(default=False, description="create only: TLS on the IngressRoute"),
            tls_secret_name: Optional[str] = Field(default=None, description="create only: TLS secret if tls_enabled"),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Simple IngressRoute (no TraefikService/WRR): create/update in place, or delete.

            create: same route_name patches in place. delete: use instead of traefik_manage_weighted_routing(delete)
            when there is no companion TraefikService.
            """
            assert self.traefik_service is not None
            assert ctx is not None

            if action == "delete":
                await ctx.info(f"Deleting simple IngressRoute '{route_name}'", extra={"route_name": route_name})
                try:
                    result = await self.traefik_service.delete_simple_ingress_route(
                        route_name=route_name,
                        namespace=namespace,
                    )
                    await ctx.info(f"Deleted IngressRoute '{route_name}'", extra={"result": result})
                    return result
                except TraefikRouteNotFoundError:
                    raise
                except Exception as e:
                    await ctx.error(f"Failed to delete simple route: {str(e)}")
                    raise TraefikOperationError(f"Simple route deletion failed: {str(e)}")

            if not routes:
                raise ValueError("action=create requires non-empty routes")

            await ctx.info(
                f"Creating/Updating simple IngressRoute '{route_name}' with {len(routes)} rule(s)",
                extra={"route_name": route_name, "namespace": namespace},
            )
            try:
                result = await self.traefik_service.create_simple_ingress_route(
                    route_name=route_name,
                    namespace=namespace,
                    entry_points=entry_points,
                    routes=routes,
                    tls_enabled=tls_enabled,
                    tls_secret_name=tls_secret_name,
                )
                await ctx.info(f"Created/Updated IngressRoute '{route_name}'", extra={"result": result})
                return result
            except (TraefikRouteConfigError, TraefikServiceError):
                raise
            except Exception as e:
                await ctx.error(f"Failed to create or update simple route: {str(e)}")
                raise TraefikOperationError(f"Simple route creation/update failed: {str(e)}")
