"""Lifecycle Tool (T10): traefik_delete_resource."""

from typing import Literal
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from traefik_mcp_server.models.schemas import ExecutionResult
from traefik_mcp_server.tools.base import BaseTool, confirm_destructive_action


class LifecycleTools(BaseTool):
    """MCP tool for safely deleting Traefik custom resources."""

    def register(self, mcp: FastMCP) -> None:
        should_reg = (
            self.should_register("traffic", is_write=True)
            or self.should_register("policies", is_write=True)
        )
        if not should_reg:
            return

        @mcp.tool(
            name="traefik_delete_resource",
            description=(
                "Delete a Traefik custom resource (IngressRoute, IngressRouteTCP, IngressRouteUDP, "
                "TraefikService, Middleware, MiddlewareTCP, TLSOption, TLSStore, ServersTransport, "
                "ServersTransportTCP) with referential-integrity and human confirmation checks. "
                "Does NOT delete Kubernetes Services, Secrets, or Gateway API resources."
            ),
            tags={"traffic", "policies", "write", "destructive"},
            annotations=ToolAnnotations(
                title="Delete Traefik Custom Resource",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def traefik_delete_resource(
            kind: Literal[
                "IngressRoute",
                "IngressRouteTCP",
                "IngressRouteUDP",
                "TraefikService",
                "Middleware",
                "MiddlewareTCP",
                "TLSOption",
                "TLSStore",
                "ServersTransport",
                "ServersTransportTCP",
            ] = Field(..., description="Traefik CRD kind to delete"),
            name: str = Field(..., min_length=1, description="Resource name to delete"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            cascade: bool = Field(
                default=False,
                description="If True, also delete unreferenced child TraefikServices/Middlewares created by this MCP server",
            ),
            force: bool = Field(
                default=False,
                description="If True, delete even when referenced by other routes (not recommended)",
            ),
            confirm: bool = Field(
                default=False,
                description="Explicit confirmation flag when MCP Elicitation is unavailable",
            ),
            ctx: Context = None,
        ) -> ExecutionResult:
            self.check_write_access("traefik_delete_resource")
            try:
                confirmed = await confirm_destructive_action(
                    ctx=ctx,
                    action_summary=(
                        f"Delete {kind} '{name}' in namespace '{namespace}' "
                        f"(cascade={cascade}, force={force})"
                    ),
                    confirm=confirm,
                )
                if not confirmed:
                    return ExecutionResult(
                        status="cancelled",
                        summary=f"Deletion of {kind} '{namespace}/{name}' cancelled: confirmation required.",
                        dry_run=False,
                        resource_uri=f"traefik://manifests/{kind}/{namespace}/{name}",
                        details={"cancelled": True, "kind": kind, "name": name, "namespace": namespace},
                    )

                res = await self.traefik_service.delete_resource(
                    kind=kind,
                    name=name,
                    namespace=namespace,
                    cascade=cascade,
                    force=force,
                )
                return ExecutionResult.model_validate(res)
            except Exception as e:
                self.handle_error(e, "traefik_delete_resource", namespace=namespace, resource_name=name)
