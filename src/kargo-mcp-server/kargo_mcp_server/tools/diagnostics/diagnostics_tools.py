"""Kargo N-to-1 diagnostics and delivery tracing tools (Toolset: diagnostics)."""

from typing import Optional
from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from kargo_mcp_server.models.schemas import (
    FreightTraceReport,
    StageDiagnosisReport,
    WarehouseDiagnosisReport,
)
from kargo_mcp_server.tools.base import BaseTool


class DiagnosticsTools(BaseTool):
    """Read-only N-to-1 diagnostic and delivery tracing tools for Kargo pipelines."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]
        """Register diagnostic tools with FastMCP."""
        if not self.should_register("diagnostics", is_write=False):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Trace Kargo Freight Delivery",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_trace_freight(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            freight_or_alias: Optional[str] = Field(
                default=None,
                description="Freight SHA-1 name or alias (e.g. 'gentle-panda'). Optional if artifact_filter is provided.",
            ),
            artifact_filter: Optional[str] = Field(
                default=None,
                description="Image tag, Git commit SHA, or Helm chart version to locate and trace across all stages.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> FreightTraceReport:
            """Trace a Freight bundle or versioned artifact across all Stages in a Kargo project (N-to-1).

            Correlates Freight artifact versions (Git commits, container images, Helm charts) with
            every Stage in the project DAG, reporting where the Freight is currently deployed,
            verified, approved, eligible for promotion, or blocked by upstream verification or soak time.
            """
            try:
                return await self.kargo_service.trace_freight(
                    project=project,
                    freight_or_alias=freight_or_alias,
                    artifact_filter=artifact_filter,
                )
            except Exception as exc:
                self.handle_error(
                    exc,
                    "kargo_trace_freight",
                    project=project,
                    resource_name=freight_or_alias or artifact_filter,
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Diagnose Kargo Stage",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_diagnose_stage(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            stage: str = Field(..., min_length=1, description="Target Stage name to diagnose."),
            include_events: bool = Field(
                default=True,
                description="Include correlated Kubernetes Warning events in the project.",
            ),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> StageDiagnosisReport:
            """Diagnose a Kargo Stage by correlating conditions, Promotion step traces, Verification AnalysisRuns, holds, and events (N-to-1).

            Returns standardized diagnosis_codes (PROMOTION_STEP_FAILED, GIT_OR_REGISTRY_AUTH_ERROR,
            ARGOCD_SYNC_OR_AUTH_FAILED, VERIFICATION_FAILED, STAGE_HEALTH_DEGRADED, AUTO_PROMOTION_ON_HOLD,
            PROMOTION_IN_PROGRESS, VERIFICATION_IN_PROGRESS, NO_FREIGHT_DEPLOYED, HEALTHY) and actionable recommendations.
            """
            try:
                return await self.kargo_service.diagnose_stage(
                    project=project,
                    stage=stage,
                    include_events=include_events,
                )
            except Exception as exc:
                self.handle_error(
                    exc,
                    "kargo_diagnose_stage",
                    project=project,
                    resource_name=stage,
                )
                raise

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Diagnose Kargo Warehouse",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def kargo_diagnose_warehouse(
            project: str = Field(..., min_length=1, description="Kargo project name."),
            warehouse: str = Field(..., min_length=1, description="Target Warehouse name to diagnose."),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> WarehouseDiagnosisReport:
            """Diagnose a Kargo Warehouse by inspecting artifact discovery status, conditions, and deprecated Kargo v1.9–v1.12 fields (N-to-1).

            Returns standardized diagnosis_codes (DEPRECATED_SUBSCRIPTION_FIELDS, WAREHOUSE_DISCOVERY_FAILED,
            REPOSITORY_AUTH_FAILED, NO_ARTIFACTS_DISCOVERED, HEALTHY) and discovered artifact counts.
            """
            try:
                return await self.kargo_service.diagnose_warehouse(
                    project=project,
                    warehouse=warehouse,
                )
            except Exception as exc:
                self.handle_error(
                    exc,
                    "kargo_diagnose_warehouse",
                    project=project,
                    resource_name=warehouse,
                )
                raise
