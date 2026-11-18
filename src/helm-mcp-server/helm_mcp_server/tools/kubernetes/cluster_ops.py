"""Kubernetes cluster prerequisite checking and session context management tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from helm_mcp_server.tools.base import BaseTool


class KubernetesTools(BaseTool):
    """Tools for checking Kubernetes cluster prerequisites and switching active session context."""

    def register(self, mcp_instance: Any) -> None:
        """Register Kubernetes execution tools with FastMCP."""

        @mcp_instance.tool(
            tags={"read"},
            annotations=ToolAnnotations(
                title="Check Kubernetes Cluster Prerequisites",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
        async def kubernetes_check_prerequisites(
            min_kubernetes_version: Optional[str] = Field(
                default=None,
                description="Minimum required Kubernetes semver (e.g., 'v1.28.0')",
            ),
            required_api_resources: Optional[List[str]] = Field(
                default=None,
                description="Required Kubernetes API resource kinds or CRDs (e.g., ['Deployment', 'Ingress', 'Certificate'])",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Verify whether the active cluster meets minimum Kubernetes version and API resource/CRD requirements."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    "Checking Kubernetes cluster prerequisites",
                    extra={
                        "min_kubernetes_version": min_kubernetes_version,
                        "required_api_resources": required_api_resources,
                    },
                )
            return await self.k8s_service.check_prerequisites(
                min_kubernetes_version=min_kubernetes_version,
                required_api_resources=required_api_resources,
                session_id=session_id,
            )

        @mcp_instance.tool(
            tags={"read", "session"},
            annotations=ToolAnnotations(
                title="Set Active Kubernetes Context",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        )
        async def kubernetes_set_context(
            context_name: str = Field(
                ...,
                min_length=1,
                description="Target kubeconfig context name (read 'kubernetes://contexts' for valid names)",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Switch the active Kubernetes cluster context for all subsequent Helm and Kubernetes calls in this session."""
            session_id = self._get_session_id(ctx)
            if ctx:
                await ctx.info(
                    f"Switching Kubernetes context to '{context_name}'",
                    extra={"context_name": context_name, "session_id": session_id},
                )
            return await self.k8s_service.set_context(
                context_name=context_name,
                session_id=session_id,
            )
