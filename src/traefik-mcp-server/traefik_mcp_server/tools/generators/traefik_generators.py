"""Generator tools for converting Deployments to Rollouts and creating supporting resources."""

import json
from typing import Dict, Any, List, Optional, Literal
from pydantic import Field
from fastmcp import Context

from traefik_mcp_server.tools.base import BaseTool


class TraefikGeneratorTools(BaseTool):
    """Tools for generating Rollout resources from Deployments."""

    async def _resolve_deployment_yaml(
        self,
        deployment_yaml: Optional[str],
        deployment_name: Optional[str],
        namespace: str,
        ctx: Context,
    ) -> str:
        """Resolve deployment YAML from either direct input or cluster fetch."""
        assert self.generator_service is not None
        assert ctx is not None
        if deployment_yaml:
            return deployment_yaml
        if deployment_name:
            await ctx.info(
                f"Auto-fetching Deployment '{deployment_name}' from namespace '{namespace}'"
            )
            return await self.generator_service.fetch_deployment_yaml(
                deployment_name=deployment_name, namespace=namespace
            )
        raise ValueError(
            "Either 'deployment_yaml' or 'deployment_name' must be provided."
        )

    def register(self, mcp_instance) -> None:
        """Register generator tools with FastMCP."""

        @mcp_instance.tool()
        async def traefik_generate_routing_manifest(
            manifest_type: Literal[
                "traefik_service",
                "ingress_for_traefik_service",
                "ingress_for_services",
                "mirroring",
                "ingress_route_tcp",
                "middleware_tcp",
            ] = Field(
                ...,
                description="Manifest type: traefik_service | ingress_for_traefik_service | ingress_for_services | mirroring | ingress_route_tcp | middleware_tcp",
            ),
            name: str = Field(
                ...,
                description="Name (semantic varies: app_name, traefik_service_name, route_name, or canary_service_name)",
            ),
            namespace: str = Field(
                default="default", description="Kubernetes namespace"
            ),
            hostname: Optional[str] = Field(
                default=None,
                description="Hostname for routing. Required for ingress_for_traefik_service, ingress_for_services.",
            ),
            stable_service: Optional[str] = Field(
                default=None,
                description="K8s Service for stable. Required for traefik_service.",
            ),
            canary_service: Optional[str] = Field(
                default=None,
                description="K8s Service for canary. Required for traefik_service.",
            ),
            routes: Optional[str] = Field(
                default=None,
                description="JSON string of route definitions. Required for ingress_for_services.",
            ),
            route_name: Optional[str] = Field(
                default=None,
                description="IngressRoute name override.",
            ),
            entry_points: Optional[List[str]] = Field(
                default=None, description="Traefik entry points"
            ),
            path_prefix: Optional[str] = Field(
                default=None, description="Path prefix match"
            ),
            tls_enabled: bool = Field(default=False, description="Enable TLS"),
            tls_secret_name: Optional[str] = Field(
                default=None, description="TLS secret name"
            ),
            traefik_version: str = Field(
                default="v3",
                description="Traefik version: 'v3' or 'v2'",
            ),
            middlewares: Optional[List[str]] = Field(
                default=None, description="Middleware names to attach"
            ),
            initial_canary_weight: int = Field(
                default=5,
                ge=0,
                le=100,
                description="Initial canary traffic % for traefik_service.",
            ),
            port: int = Field(default=80, description="Service port"),
            managed_by_argo: bool = Field(
                default=True,
                description="Omit weights for Argo management (traefik_service).",
            ),
            main_service: Optional[str] = Field(
                default=None,
                description="Main service for mirroring. Required for manifest_type=mirroring.",
            ),
            mirror_service: Optional[str] = Field(
                default=None,
                description="Mirror service for mirroring. Required for manifest_type=mirroring.",
            ),
            mirror_percent: int = Field(
                default=20,
                ge=1,
                le=100,
                description="Mirror percent for manifest_type=mirroring.",
            ),
            service_name: Optional[str] = Field(
                default=None,
                description="Backend service name. Required for ingress_route_tcp.",
            ),
            service_port: int = Field(
                default=5432,
                description="Backend service port for ingress_route_tcp.",
            ),
            sni_match: Optional[str] = Field(
                default=None,
                description="HostSNI match for ingress_route_tcp (e.g. redis.example.com or *).",
            ),
            tls_passthrough: bool = Field(
                default=False,
                description="TLS passthrough for ingress_route_tcp.",
            ),
            source_ranges: Optional[str] = Field(
                default=None,
                description="JSON array of IPs/CIDRs for middleware_tcp ipAllowList (e.g. [\"192.168.1.0/24\"]).",
            ),
            ctx: Optional[Context] = None,
        ) -> str:
            """Generate Traefik routing manifests (TraefikService, IngressRoute, TCP, etc.).

            Unified tool for YAML generation. Use manifest_type to select:
            - traefik_service: WeightedService for canary (name=app_name, stable_service, canary_service)
            - ingress_for_traefik_service: IngressRoute → TraefikService (name=traefik_service_name, hostname)
            - ingress_for_services: IngressRoute → direct K8s Services (name=route_name, hostname, routes)

            Header/cookie routing on live clusters: use ``traefik_manage_weighted_routing`` (create) with
            ``header_name`` / ``header_value`` or ``cookie_name`` / ``cookie_regex``.

            Returns:
                JSON string with generated YAML
            """
            assert self.generator_service is not None
            assert ctx is not None

            if manifest_type == "traefik_service":
                missing = []
                if not stable_service:
                    missing.append("stable_service")
                if not canary_service:
                    missing.append("canary_service")
                if missing:
                    raise ValueError(
                        f"Missing required arguments for manifest_type='traefik_service': {', '.join(missing)}"
                    )
                await ctx.info(
                    f"Creating Traefik WeightedService for {name}",
                    extra={
                        "app_name": name,
                        "stable_service": stable_service,
                        "canary_service": canary_service,
                    },
                )
                try:
                    result = (
                        await self.generator_service.create_traefik_service_for_rollout(
                            app_name=name,
                            stable_service=stable_service,
                            canary_service=canary_service,
                            namespace=namespace,
                            initial_canary_weight=initial_canary_weight,
                            port=port,
                            managed_by_argo=managed_by_argo,
                            traefik_version=traefik_version,
                        )
                    )
                    if result.get("status") == "success":
                        await ctx.info(
                            f"Created TraefikService: {result.get('stable_weight')}% stable, {result.get('canary_weight')}% canary"
                        )
                    else:
                        await ctx.error(
                            f"TraefikService creation failed: {result.get('error')}"
                        )
                    return json.dumps(result, indent=2)
                except Exception as e:
                    await ctx.error(f"Failed to create TraefikService: {str(e)}")
                    return json.dumps({"error": str(e)}, indent=2)

            elif manifest_type == "ingress_for_traefik_service":
                if not hostname or not hostname.strip():
                    raise ValueError(
                        "Missing required argument 'hostname' for manifest_type='ingress_for_traefik_service'"
                    )
                await ctx.info(
                    f"Generating IngressRoute for TraefikService '{name}' at host '{hostname}'"
                )
                try:
                    result = (
                        await self.generator_service.create_ingress_route_for_traefik_service(
                            traefik_service_name=name,
                            hostname=hostname,
                            namespace=namespace,
                            route_name=route_name,
                            entry_points=entry_points,
                            path_prefix=path_prefix,
                            tls_enabled=tls_enabled,
                            tls_secret_name=tls_secret_name,
                            traefik_version=traefik_version,
                            middlewares=middlewares,
                        )
                    )
                    if result.get("status") == "success":
                        await ctx.info(
                            f"Generated IngressRoute '{result.get('route_name')}' → TraefikService '{name}'"
                        )
                    else:
                        await ctx.error(
                            f"IngressRoute generation failed: {result.get('error')}"
                        )
                    return json.dumps(result, indent=2)
                except Exception as e:
                    await ctx.error(f"Failed to create IngressRoute: {str(e)}")
                    return json.dumps({"error": str(e)}, indent=2)

            elif manifest_type == "ingress_for_services":
                missing = []
                if not hostname or not hostname.strip():
                    missing.append("hostname")
                if not routes or not routes.strip():
                    missing.append("routes")
                if missing:
                    raise ValueError(
                        f"Missing required arguments for manifest_type='ingress_for_services': {', '.join(missing)}"
                    )
                await ctx.info(
                    f"Generating IngressRoute '{name}' for direct K8s services"
                )
                try:
                    assert routes is not None
                    parsed_routes = json.loads(routes)
                    result = (
                        await self.generator_service.create_ingress_route_for_services(
                            route_name=name,
                            hostname=hostname,
                            routes=parsed_routes,
                            namespace=namespace,
                            entry_points=entry_points,
                            tls_enabled=tls_enabled,
                            tls_secret_name=tls_secret_name,
                            traefik_version=traefik_version,
                        )
                    )
                    if result.get("status") == "success":
                        await ctx.info(
                            f"Created IngressRoute '{name}' with {len(parsed_routes)} routes"
                        )
                    else:
                        await ctx.error(
                            f"IngressRoute generation failed: {result.get('error')}"
                        )
                    return json.dumps(result, indent=2)
                except json.JSONDecodeError:
                    error_msg = "Failed to parse 'routes' JSON. Must be a valid JSON array."
                    await ctx.error(error_msg)
                    return json.dumps({"error": error_msg}, indent=2)
                except Exception as e:
                    await ctx.error(f"Failed to create IngressRoute: {str(e)}")
                    return json.dumps({"error": str(e)}, indent=2)

            elif manifest_type == "mirroring":
                missing = []
                if not main_service:
                    missing.append("main_service")
                if not mirror_service:
                    missing.append("mirror_service")
                if missing:
                    raise ValueError(
                        f"Missing required arguments for manifest_type='mirroring': {', '.join(missing)}"
                    )
                await ctx.info(f"Generating mirroring TraefikService for '{name}'")
                try:
                    result = await self.generator_service.create_mirroring_traefik_service(
                        route_name=name,
                        main_service=main_service,
                        mirror_service=mirror_service,
                        mirror_percent=mirror_percent,
                        namespace=namespace,
                        port=port,
                        traefik_version=traefik_version,
                    )
                    if result.get("status") == "success":
                        await ctx.info(f"Generated mirroring TraefikService '{result.get('service_name')}'")
                    else:
                        await ctx.error(f"Mirroring generation failed: {result.get('error')}")
                    return json.dumps(result, indent=2)
                except Exception as e:
                    await ctx.error(f"Failed to generate mirroring manifest: {str(e)}")
                    return json.dumps({"error": str(e)}, indent=2)

            elif manifest_type == "ingress_route_tcp":
                if not service_name:
                    raise ValueError("Missing required argument 'service_name' for manifest_type='ingress_route_tcp'")
                await ctx.info(f"Generating IngressRouteTCP '{name}'")
                try:
                    result = await self.generator_service.create_ingress_route_tcp(
                        route_name=name,
                        service_name=service_name,
                        service_port=service_port,
                        namespace=namespace,
                        entry_points=entry_points,
                        sni_match=sni_match,
                        tls_passthrough=tls_passthrough,
                        tls_secret_name=tls_secret_name,
                        middlewares=None,
                        traefik_version=traefik_version,
                    )
                    if result.get("status") == "success":
                        await ctx.info(f"Generated IngressRouteTCP '{result.get('route_name')}'")
                    else:
                        await ctx.error(f"IngressRouteTCP generation failed: {result.get('error')}")
                    return json.dumps(result, indent=2)
                except Exception as e:
                    await ctx.error(f"Failed to generate IngressRouteTCP: {str(e)}")
                    return json.dumps({"error": str(e)}, indent=2)

            elif manifest_type == "middleware_tcp":
                if not source_ranges or not source_ranges.strip():
                    raise ValueError("Missing required argument 'source_ranges' for manifest_type='middleware_tcp'")
                await ctx.info(f"Generating MiddlewareTCP '{name}'")
                try:
                    parsed_ranges = json.loads(source_ranges)
                    if not isinstance(parsed_ranges, list):
                        raise ValueError("source_ranges must be a JSON array")
                    result = await self.generator_service.create_middleware_tcp_ip_allowlist(
                        middleware_name=name,
                        source_ranges=parsed_ranges,
                        namespace=namespace,
                        traefik_version=traefik_version,
                    )
                    if result.get("status") == "success":
                        await ctx.info(f"Generated MiddlewareTCP '{result.get('middleware_name')}'")
                    else:
                        await ctx.error(f"MiddlewareTCP generation failed: {result.get('error')}")
                    return json.dumps(result, indent=2)
                except json.JSONDecodeError:
                    return json.dumps({"error": "source_ranges must be valid JSON array"}, indent=2)
                except Exception as e:
                    await ctx.error(f"Failed to generate MiddlewareTCP: {str(e)}")
                    return json.dumps({"error": str(e)}, indent=2)

