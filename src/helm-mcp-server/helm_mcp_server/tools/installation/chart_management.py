"""Helm release mutation tools: install, upgrade, rollback, and uninstall."""

from typing import Any, Dict, Literal, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from helm_mcp_server.tools.base import BaseTool


class ChartManagementTools(BaseTool):
    """Mutating tools for managing Helm release lifecycles on Kubernetes."""

    def register(self, mcp_instance: Any) -> None:
        """Register release lifecycle tools with FastMCP."""

        @mcp_instance.tool(
            tags={"mutate"},
            annotations=ToolAnnotations(
                title="Install Helm Chart",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            ),
        )
        async def helm_install_chart(
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
            values: Dict[str, Any] = Field(
                default_factory=dict,
                description="Values override dictionary passed via -f",
            ),
            version: Optional[str] = Field(
                default=None,
                description="Optional chart version constraint (e.g., '15.5.0')",
            ),
            create_namespace: bool = Field(
                default=False,
                description="Create target namespace if it does not exist",
            ),
            skip_crds: bool = Field(
                default=False,
                description="Skip installing CRDs bundled in chart's crds/ directory",
            ),
            wait_timeout: Optional[str] = Field(
                default=None,
                description="Optional Helm --wait timeout duration (e.g., '5m', '300s')",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Install a new Helm release onto the active Kubernetes cluster context.

            Returns concise deployment summary:
            {"status", "release_name", "namespace", "revision", "chart", "chart_version", "total_resources", "resource_counts"}.
            """
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Installing chart '{chart_ref}' as release '{release_name}' in namespace '{namespace}'",
                    extra={"chart_ref": chart_ref, "release_name": release_name, "namespace": namespace},
                )
            return await self.helm_service.install_chart(
                chart_ref=chart_ref,
                release_name=release_name,
                namespace=namespace,
                values=values,
                version=version,
                create_namespace=create_namespace,
                skip_crds=skip_crds,
                wait_timeout=wait_timeout,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"mutate"},
            annotations=ToolAnnotations(
                title="Upgrade Helm Release",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            ),
        )
        async def helm_upgrade_release(
            release_name: str = Field(
                ...,
                min_length=1,
                description="Existing Helm release name to upgrade",
            ),
            chart_ref: str = Field(
                ...,
                min_length=1,
                description="Explicit chart reference in '<repo>/<chart>' or 'oci://...' format",
            ),
            namespace: str = Field(
                default="default",
                description="Target Kubernetes namespace",
            ),
            values: Dict[str, Any] = Field(
                default_factory=dict,
                description="Values override dictionary passed via -f",
            ),
            version: Optional[str] = Field(
                default=None,
                description="Target chart version (e.g., '15.5.0')",
            ),
            values_strategy: Literal["reuse", "reset", "reset_then_reuse"] = Field(
                default="reuse",
                description="How to merge previous release values: 'reuse' (--reuse-values), 'reset' (--reset-values), or 'reset_then_reuse' (--reset-then-reuse-values)",
            ),
            wait_timeout: Optional[str] = Field(
                default=None,
                description="Optional Helm --wait timeout duration (e.g., '5m', '300s')",
            ),
            atomic: bool = Field(
                default=False,
                description="Automatically roll back on upgrade failure (--atomic)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Upgrade an existing Helm release to a new chart version or values configuration.

            Returns concise deployment summary:
            {"status", "release_name", "namespace", "revision", "chart", "chart_version", "total_resources", "resource_counts"}.
            """
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Upgrading release '{release_name}' in namespace '{namespace}'",
                    extra={"release_name": release_name, "chart_ref": chart_ref, "namespace": namespace},
                )
            return await self.helm_service.upgrade_release(
                release_name=release_name,
                chart_ref=chart_ref,
                namespace=namespace,
                values=values,
                version=version,
                values_strategy=values_strategy,
                wait_timeout=wait_timeout,
                atomic=atomic,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"mutate"},
            annotations=ToolAnnotations(
                title="Rollback Helm Release",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            ),
        )
        async def helm_rollback_release(
            release_name: str = Field(
                ...,
                min_length=1,
                description="Helm release name to roll back",
            ),
            namespace: str = Field(
                default="default",
                description="Kubernetes namespace of the release",
            ),
            revision: Optional[int] = Field(
                default=None,
                ge=1,
                description="Target revision number from helm://releases/{namespace}/{release}/history (omit for previous revision)",
            ),
            wait_timeout: Optional[str] = Field(
                default=None,
                description="Optional Helm --wait timeout duration (e.g., '5m')",
            ),
            dry_run: bool = Field(
                default=False,
                description="Simulate rollback without modifying cluster state",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Roll back a Helm release to a previous revision (or simulate with dry_run=True)."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Rolling back release '{release_name}' in namespace '{namespace}' (revision={revision}, dry_run={dry_run})",
                    extra={"release_name": release_name, "namespace": namespace, "revision": revision, "dry_run": dry_run},
                )
            return await self.helm_service.rollback_release(
                release_name=release_name,
                namespace=namespace,
                revision=revision,
                wait_timeout=wait_timeout,
                dry_run=dry_run,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"mutate"},
            annotations=ToolAnnotations(
                title="Uninstall Helm Release",
                readOnlyHint=False,
                destructiveHint=True,
                idempotentHint=False,
                openWorldHint=True,
            ),
        )
        async def helm_uninstall_release(
            release_name: str = Field(
                ...,
                min_length=1,
                description="Helm release name to uninstall",
            ),
            namespace: str = Field(
                default="default",
                description="Kubernetes namespace of the release",
            ),
            keep_history: bool = Field(
                default=False,
                description="Retain release history after deleting Kubernetes resources (--keep-history)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Uninstall a Helm release and delete its managed Kubernetes resources."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.warning(
                    f"Uninstalling release '{release_name}' from namespace '{namespace}'",
                    extra={"release_name": release_name, "namespace": namespace, "keep_history": keep_history},
                )
            return await self.helm_service.uninstall_release(
                release_name=release_name,
                namespace=namespace,
                keep_history=keep_history,
                session_id=session_id,
            )
