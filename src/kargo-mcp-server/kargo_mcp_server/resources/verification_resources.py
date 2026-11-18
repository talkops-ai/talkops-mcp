"""Kargo verification AnalysisTemplate, AnalysisRun, and logs resources."""

import json
from typing import Any, Dict, List

from kargo_mcp_server.resources.base import BaseResource
from kargo_mcp_server.utils.redaction import sanitize_manifest


class VerificationResources(BaseResource):
    """Verification AnalysisTemplates, AnalysisRun status, and AnalysisRun logs MCP resources."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://projects/{project}/analysis-templates",
            name="kargo_project_analysis_templates",
            description="Project AnalysisTemplates and cluster-scoped ClusterAnalysisTemplates available for Stage verification",
            mime_type="application/json",
        )
        async def list_analysis_templates_resource(project: str) -> str:
            """List AnalysisTemplates and ClusterAnalysisTemplates."""
            try:
                data = await self.kargo_service.list_analysis_templates(
                    project, include_cluster=True
                )

                def _summarize(items: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
                    out: List[Dict[str, Any]] = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        meta = item.get("metadata") or {}
                        spec = item.get("spec") or {}
                        metrics = spec.get("metrics") or []
                        out.append(
                            {
                                "name": meta.get("name", ""),
                                "kind": item.get("kind", kind),
                                "metrics_count": len(metrics),
                                "metric_names": [
                                    m.get("name", "") for m in metrics if isinstance(m, dict)
                                ],
                                "args": [
                                    a.get("name", "")
                                    for a in (spec.get("args") or [])
                                    if isinstance(a, dict)
                                ],
                            }
                        )
                    return out

                payload = {
                    "project": project,
                    "analysis_templates": _summarize(
                        data.get("analysis_templates") or [], "AnalysisTemplate"
                    ),
                    "cluster_analysis_templates": _summarize(
                        data.get("cluster_analysis_templates") or [],
                        "ClusterAnalysisTemplate",
                    ),
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps({"project": project, "error": str(exc)}, indent=2)

        @mcp_instance.resource(
            "kargo://projects/{project}/analysis-runs/{run}",
            name="kargo_analysis_run_detail",
            description="Verification AnalysisRun status and metric results",
            mime_type="application/json",
        )
        async def get_analysis_run_resource(project: str, run: str) -> str:
            """Get sanitized verification AnalysisRun status."""
            try:
                raw = await self.kargo_service.get_analysis_run(project, run)
                sanitized = sanitize_manifest(raw) if isinstance(raw, dict) else raw
                status = (sanitized.get("status") or {}) if isinstance(sanitized, dict) else {}
                payload = {
                    "name": run,
                    "project": project,
                    "phase": status.get("phase", "Unknown"),
                    "message": status.get("message"),
                    "metric_results": status.get("metricResults") or [],
                    "started_at": status.get("startedAt"),
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps(
                    {"project": project, "run": run, "error": str(exc)}, indent=2
                )

        @mcp_instance.resource(
            "kargo://projects/{project}/analysis-runs/{run}/logs",
            name="kargo_analysis_run_logs",
            description="Job-metric container logs for a verification AnalysisRun",
            mime_type="application/json",
        )
        async def get_analysis_run_logs_resource(project: str, run: str) -> str:
            """Get job metric logs for a verification AnalysisRun."""
            try:
                logs = await self.kargo_service.get_analysis_run_logs(project, run)
                return json.dumps(
                    {"project": project, "run": run, "logs": logs},
                    indent=2,
                    default=str,
                )
            except Exception as exc:
                return json.dumps(
                    {"project": project, "run": run, "error": str(exc)}, indent=2
                )
