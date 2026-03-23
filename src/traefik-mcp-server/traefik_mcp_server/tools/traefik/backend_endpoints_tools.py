"""MCP tools for Traefik ServersTransport and Service sticky-session annotations."""

from typing import Any, Dict, Literal, Optional

from pydantic import Field
from fastmcp import Context

from traefik_mcp_server.tools.base import BaseTool
from traefik_mcp_server.services.traefik_service import TRAEFIK_STICKY_SERVICE_ANNOTATION_KEYS
from traefik_mcp_server.exceptions.custom import TraefikOperationError, TraefikServiceError


class TraefikBackendEndpointsTools(BaseTool):
    """ServersTransport CRDs and Traefik sticky annotations on Kubernetes Services."""

    def register(self, mcp_instance) -> None:
        """Register backend endpoint tools."""

        @mcp_instance.tool()
        async def traefik_manage_servers_transport(
            action: Literal["create", "delete"] = Field(
                ...,
                description="create: upsert ServersTransport | delete: remove by name",
            ),
            name: str = Field(..., min_length=1, description="ServersTransport resource name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            dial_timeout: Optional[str] = Field(
                default=None,
                description="create only: e.g. 30s, 1m — maps to spec.forwardingTimeouts.dialTimeout",
            ),
            response_header_timeout: Optional[str] = Field(
                default=None,
                description="create only: e.g. 60s — spec.forwardingTimeouts.responseHeaderTimeout",
            ),
            insecure_skip_verify: bool = Field(
                default=False,
                description="create only: set spec.insecureSkipVerify for HTTPS backends",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Create/update or delete a Traefik ServersTransport (backend TLS/timeouts).

            Link a Service with annotation ``traefik.ingress.kubernetes.io/service.serverstransport``:
            ``<namespace>-<transport-name>@kubernetescrd``.
            """
            assert self.traefik_service is not None
            if action == "delete":
                if ctx:
                    await ctx.info(f"Deleting ServersTransport '{name}' in {namespace}")
                try:
                    return await self.traefik_service.delete_servers_transport(
                        name=name,
                        namespace=namespace,
                    )
                except TraefikServiceError as e:
                    if ctx:
                        await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"delete ServersTransport failed: {e}")

            if ctx:
                await ctx.info(f"Upserting ServersTransport '{name}' in {namespace}")
            try:
                return await self.traefik_service.build_and_upsert_servers_transport(
                    name=name,
                    namespace=namespace,
                    dial_timeout=dial_timeout,
                    response_header_timeout=response_header_timeout,
                    insecure_skip_verify=insecure_skip_verify,
                )
            except TraefikServiceError as e:
                if ctx:
                    await ctx.error(str(e))
                raise
            except Exception as e:
                raise TraefikOperationError(f"create ServersTransport failed: {e}")

        @mcp_instance.tool()
        async def traefik_configure_service_affinity(
            action: Literal["enable", "disable"] = Field(
                ...,
                description="enable: set Traefik sticky cookie annotations on the Service | disable: remove them",
            ),
            service_name: str = Field(..., min_length=1, description="Kubernetes Service name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            cookie_name: Optional[str] = Field(
                default=None,
                description="enable only: traefik.ingress.kubernetes.io/service.sticky.cookie.name",
            ),
            cookie_max_age: Optional[str] = Field(
                default=None,
                description="enable only: service.sticky.cookie.maxage (e.g. 3600)",
            ),
            cookie_samesite: Optional[str] = Field(
                default=None,
                description="enable only: service.sticky.cookie.samesite (e.g. Lax)",
            ),
            cookie_secure: Optional[str] = Field(
                default=None,
                description="enable only: service.sticky.cookie.secure (e.g. true)",
            ),
            ctx: Optional[Context] = None,
        ) -> Dict[str, Any]:
            """Enable or disable Traefik sticky-session annotations on a Kubernetes Service.

            Matches NGINX migration mapping (affinity cookie → Service annotations).
            """
            assert self.traefik_service is not None
            prefix = "traefik.ingress.kubernetes.io/"
            if action == "disable":
                if ctx:
                    await ctx.info(
                        f"Stripping sticky annotations from Service '{service_name}'/{namespace}"
                    )
                try:
                    return await self.traefik_service.strip_service_annotation_keys(
                        name=service_name,
                        namespace=namespace,
                        keys=TRAEFIK_STICKY_SERVICE_ANNOTATION_KEYS,
                    )
                except TraefikServiceError as e:
                    if ctx:
                        await ctx.error(str(e))
                    raise
                except Exception as e:
                    raise TraefikOperationError(f"disable service affinity failed: {e}")

            annotations: Dict[str, str] = {f"{prefix}service.sticky.cookie": "true"}
            if cookie_name and str(cookie_name).strip():
                annotations[f"{prefix}service.sticky.cookie.name"] = cookie_name.strip()
            if cookie_max_age and str(cookie_max_age).strip():
                annotations[f"{prefix}service.sticky.cookie.maxage"] = cookie_max_age.strip()
            if cookie_samesite and str(cookie_samesite).strip():
                annotations[f"{prefix}service.sticky.cookie.samesite"] = cookie_samesite.strip()
            if cookie_secure is not None and str(cookie_secure).strip():
                annotations[f"{prefix}service.sticky.cookie.secure"] = str(cookie_secure).strip()

            if ctx:
                await ctx.info(
                    f"Enabling sticky session annotations on Service '{service_name}'/{namespace}"
                )
            try:
                return await self.traefik_service.merge_service_annotations(
                    name=service_name,
                    namespace=namespace,
                    annotations=annotations,
                )
            except TraefikServiceError as e:
                if ctx:
                    await ctx.error(str(e))
                raise
            except Exception as e:
                raise TraefikOperationError(f"enable service affinity failed: {e}")
