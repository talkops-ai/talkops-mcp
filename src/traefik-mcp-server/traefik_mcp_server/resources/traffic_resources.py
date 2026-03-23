"""Traffic distribution resources.

Provides real-time traffic weight distribution and full route inspection
from Traefik routes via the MCP resource protocol.
"""

import json
from typing import List
from mcp.types import Resource, TextContent
from traefik_mcp_server.resources.base import BaseResource



class TrafficResources(BaseResource):
    """Traffic distribution resources.

    Provides live traffic weights and full route inspection from Traefik.
    """

    def register(self, mcp_instance) -> None:
        """Register traffic resources with FastMCP."""

        @mcp_instance.resource("traefik://traffic/{namespace}/{route_name}/distribution")
        async def traffic_distribution(namespace: str, route_name: str) -> str:
            """Full route inspection — weights, middlewares, entrypoints, linked Rollout.

            Returns a comprehensive snapshot of the route in one call:
            - IngressRoute match rule, entrypoints, attached middleware names
            - TraefikService stable/canary weight split with percentages
            - Each middleware's CRD spec (rate limit, circuit breaker, etc.)
            - Which Argo Rollout (if any) has trafficRouting pointing here

            If linked_rollout is null, run argo_set_traffic_routing to connect
            the Rollout to this TraefikService.

            Args:
                namespace: Kubernetes namespace
                route_name: IngressRoute name (TraefikService inferred as {route_name}-wrr)

            Returns:
                JSON string with full route inspection result
            """
            try:
                if not self.traefik_service:
                    return json.dumps({
                        "error": "Traefik service not available",
                        "route": route_name,
                        "namespace": namespace
                    }, indent=2)

                result = await self.traefik_service.inspect_route(
                    route_name=route_name,
                    namespace=namespace,
                )
                return json.dumps(result, indent=2)

            except Exception as e:
                return json.dumps({
                    "error": str(e),
                    "route": route_name,
                    "namespace": namespace
                }, indent=2)

        @mcp_instance.resource("traefik://traffic/routes/list")
        async def list_traffic_routes() -> str:
            """List all TraefikService CRDs across ALL namespaces.

            Returns each TraefikService with:
            - Name, namespace, type (weighted/mirror)
            - Backend K8s services, weights, percentages
            - argo_managed flag (True = Argo Rollouts is controlling weights)

            For per-route full detail (middlewares + linked Rollout), read:
                traefik://traffic/{namespace}/{route_name}/distribution

            Returns:
                JSON string with cluster-wide list of TraefikServices grouped by namespace
            """
            try:
                if not self.traefik_service:
                    return json.dumps({"error": "Traefik service not available"}, indent=2)

                # namespace=None means cluster-wide
                result = await self.traefik_service.list_traefik_services(
                    namespace=None,
                )
                return json.dumps(result, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)

        @mcp_instance.resource("traefik://traffic/ingressroutes/list")
        async def list_ingress_routes() -> str:
            """List all IngressRoute CRDs across ALL namespaces.

            Returns each IngressRoute with:
            - Name, namespace
            - Match rules and endpoints
            - Target resources (TraefikServices or K8s Services)
            - Middlewares attached

            For TraefikServices inventory, read:
                traefik://traffic/routes/list

            Returns:
                JSON string with cluster-wide list of IngressRoutes
            """
            try:
                if not self.traefik_service:
                    return json.dumps({"error": "Traefik service not available"}, indent=2)

                result = await self.traefik_service.list_ingress_routes(
                    namespace=None,
                )
                return json.dumps(result, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)

        @mcp_instance.resource("traefik://traffic/tcp/list")
        async def list_tcp_routes() -> str:
            """List all IngressRouteTCP CRDs across ALL namespaces.

            Returns each IngressRouteTCP with:
            - Name, namespace
            - Match rules (SNI) and endpoints
            - Target resources (Backend K8s Services with ports)
            - Attached MiddlewareTCP objects
            - TLS passthrough status

            Returns:
                JSON string with cluster-wide list of TCP IngressRoutes
            """
            try:
                if not self.traefik_service:
                    return json.dumps({"error": "Traefik service not available"}, indent=2)

                result = await self.traefik_service.list_tcp_routes(
                    namespace=None,
                )
                return json.dumps(result, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)
