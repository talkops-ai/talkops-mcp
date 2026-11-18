"""Helm release inspection, manifest rendering, release planning (diff), and deployment health monitoring tools."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from helm_mcp_server.tools.base import BaseTool


class MonitoringTools(BaseTool):
    """Read-tier and N-to-1 analytical tools for Helm releases and Kubernetes workloads."""

    def register(self, mcp_instance: Any) -> None:
        """Register release inspection, planning, and monitoring tools with FastMCP."""

        @mcp_instance.tool(
            tags={"read"},
            annotations=ToolAnnotations(
                title="List Helm Releases",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def helm_list_releases(
            namespace: Optional[str] = Field(
                default=None,
                description="Namespace filter (omit to list releases across all namespaces)",
            ),
            status: Optional[Literal["deployed", "failed", "pending", "superseded", "uninstalled", "uninstalling"]] = Field(
                default=None,
                description="Optional release status filter",
            ),
            limit: int = Field(
                default=50,
                ge=1,
                le=250,
                description="Maximum number of releases to return (1-250)",
            ),
            offset: int = Field(
                default=0,
                ge=0,
                description="Pagination offset",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """List Helm releases in the active cluster with optional namespace/status filtering and pagination."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    "Listing Helm releases",
                    extra={"namespace": namespace, "status": status, "limit": limit, "offset": offset},
                )
            return await self.helm_service.list_releases(
                namespace=namespace,
                status=status,
                limit=limit,
                offset=offset,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"read"},
            annotations=ToolAnnotations(
                title="Get Helm Release Status",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def helm_get_release_status(
            release_name: str = Field(
                ...,
                min_length=1,
                description="Helm release name",
            ),
            namespace: str = Field(
                default="default",
                description="Kubernetes namespace of the release",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Get concise current status, revision, resource counts, and resource URIs for a Helm release."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Fetching status for release '{release_name}' in namespace '{namespace}'",
                    extra={"release_name": release_name, "namespace": namespace},
                )
            return await self.helm_service.get_release_status(
                release_name=release_name,
                namespace=namespace,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"read"},
            annotations=ToolAnnotations(
                title="Render Helm Chart Manifests",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def helm_render_manifests(
            chart_ref: str = Field(
                ...,
                min_length=1,
                description="Explicit chart reference in '<repo>/<chart>' or 'oci://...' format",
            ),
            namespace: str = Field(
                default="default",
                description="Target Kubernetes namespace",
            ),
            values: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Optional values override dictionary",
            ),
            version: Optional[str] = Field(
                default=None,
                description="Optional chart version (e.g., '15.5.0')",
            ),
            include_full: bool = Field(
                default=False,
                description="Include complete rendered YAML manifests in addition to summary and preview",
            ),
            preview_lines: int = Field(
                default=100,
                ge=10,
                le=500,
                description="Number of lines to include in YAML preview (10-500)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Render Kubernetes manifests from a Helm chart offline with automatic Secret data redaction."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Rendering manifests for chart '{chart_ref}'",
                    extra={"chart_ref": chart_ref, "namespace": namespace, "version": version},
                )
            return await self.helm_service.render_manifests(
                chart_ref=chart_ref,
                namespace=namespace,
                values=values,
                version=version,
                include_full=include_full,
                preview_lines=preview_lines,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"read"},
            annotations=ToolAnnotations(
                title="Plan Helm Release (Install Preview & Upgrade Diff)",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def helm_plan_release(
            chart_ref: str = Field(
                ...,
                min_length=1,
                description="Explicit chart reference in '<repo>/<chart>' or 'oci://...' format",
            ),
            release_name: str = Field(
                ...,
                min_length=1,
                description="Target Helm release name",
            ),
            namespace: str = Field(
                default="default",
                description="Target Kubernetes namespace",
            ),
            values: Optional[Dict[str, Any]] = Field(
                default=None,
                description="Proposed values override dictionary",
            ),
            version: Optional[str] = Field(
                default=None,
                description="Target chart version",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Compute a pre-deployment plan for a Helm release (install preview if new; resource/image/replica diff if existing)."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Planning release '{release_name}' ({chart_ref}) in namespace '{namespace}'",
                    extra={"chart_ref": chart_ref, "release_name": release_name, "namespace": namespace},
                )
            return await self.helm_service.plan_release(
                chart_ref=chart_ref,
                release_name=release_name,
                namespace=namespace,
                values=values,
                version=version,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"read"},
            annotations=ToolAnnotations(
                title="Monitor Helm Deployment Health",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def helm_monitor_deployment(
            release_name: str = Field(
                ...,
                min_length=1,
                description="Helm release name to monitor",
            ),
            namespace: str = Field(
                default="default",
                description="Kubernetes namespace of the release",
            ),
            max_wait_seconds: int = Field(
                default=60,
                ge=1,
                le=300,
                description="Maximum time to poll for readiness in seconds (1-300)",
            ),
            check_interval: int = Field(
                default=5,
                ge=1,
                le=30,
                description="Polling interval in seconds (1-30)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Evaluate Helm release status, Deployment/StatefulSet rollouts, and container failure states."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Monitoring deployment health for release '{release_name}' in namespace '{namespace}'",
                    extra={"release_name": release_name, "namespace": namespace, "max_wait_seconds": max_wait_seconds},
                )
            return await self.helm_service.monitor_deployment_health(
                release_name=release_name,
                namespace=namespace,
                max_wait_seconds=max_wait_seconds,
                check_interval=check_interval,
                session_id=session_id,
            )
