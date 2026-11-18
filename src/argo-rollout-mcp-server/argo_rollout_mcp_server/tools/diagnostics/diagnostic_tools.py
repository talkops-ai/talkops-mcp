"""Single-call rollout diagnosis tool for troubleshooting degraded or paused Rollouts."""

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from argo_rollout_mcp_server.models.schemas import RolloutDiagnosisReport
from argo_rollout_mcp_server.tools.base import BaseTool


class DiagnosticTools(BaseTool):
    """Read-only diagnostic toolset for Argo Rollouts."""

    def register(self, mcp_instance) -> None:
        """Register diagnostic tools with FastMCP."""
        if not self.should_register("diagnostics", is_write=False):
            return

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Diagnose Argo Rollout",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def argo_diagnose_rollout(
            name: str = Field(..., min_length=1, description="Rollout name"),
            namespace: str = Field(default="default", description="Kubernetes namespace"),
            include_events: bool = Field(
                default=True,
                description="Include Warning Kubernetes events for the Rollout and its pods",
            ),
            include_analysis: bool = Field(
                default=True,
                description="Include recent AnalysisRuns and failing metric measurements",
            ),
            include_pods: bool = Field(
                default=False,
                description="Include per-pod status, restart counts, and container waiting reasons",
            ),
            ctx: Context = None,
        ) -> RolloutDiagnosisReport:
            """Collect a single-call diagnostic report with deterministic diagnosis codes for a Rollout."""
            try:
                report = await self.argo_service.diagnose_rollout(
                    name=name,
                    namespace=namespace,
                    include_events=include_events,
                    include_analysis=include_analysis,
                    include_pods=include_pods,
                )
                return RolloutDiagnosisReport(
                    name=report.get("name", name),
                    namespace=report.get("namespace", namespace),
                    phase=report.get("phase", "Unknown"),
                    strategy=report.get("strategy", "unknown"),
                    summary=report.get("summary", ""),
                    diagnosis_codes=report.get("diagnosis_codes", []),
                    current_step=report.get("current_step"),
                    canary_weight=report.get("canary_weight"),
                    replicas=report.get("replicas", {}),
                    conditions=report.get("conditions", []),
                    failing_metrics=report.get("failing_metrics", []),
                    warning_events=report.get("warning_events", []),
                    pods=report.get("pods", []),
                )
            except Exception as e:
                self.handle_error(e, "argo_diagnose_rollout", namespace=namespace, resource_name=name)
