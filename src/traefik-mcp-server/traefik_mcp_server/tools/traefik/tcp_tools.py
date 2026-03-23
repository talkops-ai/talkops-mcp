"""Traefik TCP routing and middleware tools."""

from typing import Dict, Any, Optional, List, Literal
from pydantic import Field
from fastmcp import Context

from traefik_mcp_server.tools.base import BaseTool
from traefik_mcp_server.exceptions.custom import (
    TraefikOperationError,
    TraefikRouteNotFoundError,
    TraefikServiceError,
    TraefikMiddlewareError,
    KubernetesResourceError,
)


class TraefikTCPTools(BaseTool):
    """Tools for TCP routing and TCP middleware management."""

    def register(self, mcp_instance) -> None:
        """Register TCP tools with FastMCP."""

        @mcp_instance.tool()
        async def traefik_manage_tcp_routing(
            route_name: str = Field(..., min_length=1, description="IngressRouteTCP name"),
            action: Literal["create", "delete"] = Field(
                ...,
                description="Action: create or delete",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            service_name: Optional[str] = Field(
                default=None,
                description="Backend K8s Service name. Required for action=create.",
            ),
            service_port: int = Field(
                default=5432,
                description="Backend service port. For action=create.",
            ),
            entry_points: Optional[List[str]] = Field(
                default=None,
                description='TCP entry points (default: ["postgresql"]). For action=create.',
            ),
            sni_match: Optional[str] = Field(
                default=None,
                description="HostSNI match (e.g. redis.example.com or *). For action=create.",
            ),
            tls_passthrough: bool = Field(
                default=False,
                description="TLS passthrough to backend. For action=create.",
            ),
            tls_secret_name: Optional[str] = Field(
                default=None,
                description="TLS secret for termination. For action=create.",
            ),
            middlewares: Optional[List[str]] = Field(
                default=None,
                description="MiddlewareTCP names to attach. For action=create.",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Manage TCP routing (IngressRouteTCP) for non-HTTP services.

            Use for PostgreSQL, Redis, MQTT, or other TCP protocols.
            Requires Traefik with IngressRouteTCP CRD installed.

            Args:
                route_name: IngressRouteTCP name
                action: create | delete
                namespace: Kubernetes namespace
                service_name: Backend service (required for create)
                service_port: Backend port (default 5432)
                entry_points: TCP entry points
                sni_match: HostSNI match (* for catch-all)
                tls_passthrough: Forward TLS to backend
                tls_secret_name: TLS secret for termination
                middlewares: MiddlewareTCP names

            Returns:
                Creation or deletion result
            """
            assert self.traefik_service is not None
            assert ctx is not None

            if action == "create":
                if not service_name or not service_name.strip():
                    raise ValueError("service_name is required for action=create")
                await ctx.info(
                    f"Creating IngressRouteTCP '{route_name}' for {service_name}:{service_port}"
                )
                try:
                    result = await self.traefik_service.create_ingress_route_tcp(
                        route_name=route_name,
                        service_name=service_name,
                        service_port=service_port,
                        namespace=namespace,
                        entry_points=entry_points,
                        sni_match=sni_match,
                        tls_passthrough=tls_passthrough,
                        tls_secret_name=tls_secret_name,
                        middlewares=middlewares,
                    )
                    await ctx.info(f"Successfully created IngressRouteTCP '{route_name}'")
                    return result
                except KubernetesResourceError as e:
                    await ctx.error(str(e))
                    raise
                except TraefikServiceError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(str(e))
                    raise TraefikOperationError(f"Failed to create IngressRouteTCP: {e}")
            elif action == "delete":
                await ctx.info(f"Deleting IngressRouteTCP '{route_name}'")
                try:
                    result = await self.traefik_service.delete_ingress_route_tcp(
                        route_name=route_name,
                        namespace=namespace,
                    )
                    await ctx.info(f"Successfully deleted IngressRouteTCP '{route_name}'")
                    return result
                except TraefikRouteNotFoundError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(str(e))
                    raise TraefikOperationError(f"Failed to delete IngressRouteTCP: {e}")
            else:
                raise ValueError(f"Invalid action: {action}. Use 'create' or 'delete'.")

        @mcp_instance.tool()
        async def traefik_configure_tcp_middleware(
            middleware_name: str = Field(..., min_length=1, description="MiddlewareTCP name"),
            action: Literal["create", "delete"] = Field(
                default="create",
                description="Action: create (or update proxy) | delete",
            ),
            middleware_type: str = Field(
                default="ip_allowlist",
                description="Type: ip_allowlist (only supported type)",
            ),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            source_ranges: Optional[str] = Field(
                default=None,
                description='JSON array of allowed IPs/CIDRs (e.g. ["192.168.1.0/24", "10.0.0.1"]). Required for create.',
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Create, update, or delete a MiddlewareTCP for TCP IP restriction (ipAllowList).

            Restrict which client IPs can connect to TCP services (e.g. databases).

            Args:
                middleware_name: MiddlewareTCP name
                action: create or delete
                middleware_type: ip_allowlist (only supported)
                namespace: Kubernetes namespace
                source_ranges: JSON array of allowed IPs/CIDRs

            Returns:
                Creation or deletion result
            """
            assert self.traefik_service is not None
            assert ctx is not None

            if action == "create":
                if middleware_type != "ip_allowlist":
                    raise ValueError("Only middleware_type='ip_allowlist' is supported")
                if not source_ranges or not source_ranges.strip():
                    raise ValueError("source_ranges is required for create (JSON array)")
                import json
                try:
                    ranges = json.loads(source_ranges)
                    if not isinstance(ranges, list):
                        raise ValueError("source_ranges must be a JSON array")
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON for source_ranges: {e}")
                await ctx.info(
                    f"Creating/Updating MiddlewareTCP '{middleware_name}' with ipAllowList"
                )
                try:
                    result = await self.traefik_service.create_middleware_tcp_ip_allowlist(
                        middleware_name=middleware_name,
                        source_ranges=ranges,
                        namespace=namespace,
                    )
                    await ctx.info(f"Successfully configured MiddlewareTCP '{middleware_name}'")
                    return result
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except KubernetesResourceError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(str(e))
                    raise TraefikOperationError(f"Failed to configure MiddlewareTCP: {e}")
            elif action == "delete":
                await ctx.info(f"Deleting MiddlewareTCP '{middleware_name}'")
                try:
                    result = await self.traefik_service.delete_middleware_tcp(
                        middleware_name=middleware_name,
                        namespace=namespace,
                    )
                    await ctx.info(f"Successfully deleted MiddlewareTCP '{middleware_name}'")
                    return result
                except TraefikMiddlewareError as e:
                    await ctx.error(str(e))
                    raise
                except Exception as e:
                    await ctx.error(str(e))
                    raise TraefikOperationError(f"Failed to delete MiddlewareTCP: {e}")
            else:
                raise ValueError(f"Invalid action: {action}")
