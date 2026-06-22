"""Tempo diagnostics tool.

Aggregates multiple health and status endpoints into a single
curated diagnostics view with actionable findings.
"""

from typing import Any, Dict, List, Optional

from mcp.types import ToolAnnotations
from fastmcp import Context
from pydantic import Field

from tempo_mcp_server.exceptions import TempoOperationError
from tempo_mcp_server.tools.base import BaseTool


class DiagnosticsTools(BaseTool):
    """Backend diagnostics and health analysis tools."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        tempo_service = self.tempo_service

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Get Tempo Diagnostics",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
            output_schema=None,
        )
        async def tempo_get_diagnostics(
            backend_id: str = Field(..., min_length=1, description="Tempo backend ID"),
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Dict[str, Any]:
            """Run comprehensive diagnostics on a Tempo backend.

            HIGH-INTENT: Aggregates health check, build info, service status,
            and ring status into a curated diagnostics report with severity-ranked
            findings and suggested actions. Read-only.

            Returns:
            - {"status": "healthy"|"degraded"|"unhealthy", "ready": bool,
               "build_info": {...}, "services": {...}, "findings": [...],
               "issues": int}

            When NOT to use: For simple health check, use tempo_list_backends.
            For query limits, use tempo_get_query_policies.

            Common errors:
            - Backend unreachable: Verify network connectivity and base URL.
            """
            findings: List[Dict[str, Any]] = []
            overall_status = "healthy"

            try:
                if ctx:
                    await ctx.info(f"Running diagnostics on backend '{backend_id}'...")
                # 1. Health check
                health = await tempo_service.check_health(backend_id)
                is_ready = health.get("ready", False)
                if not is_ready:
                    overall_status = "unhealthy"
                    findings.append({
                        "category": "health",
                        "severity": "critical",
                        "message": f"Backend not ready: {health.get('error', 'unknown')}",
                        "suggested_action": "Check Tempo logs and verify the service is running.",
                    })

                # 2. Build info
                build_info = None
                try:
                    build_info = await tempo_service.get_build_info(backend_id)
                except Exception as e:
                    findings.append({
                        "category": "health",
                        "severity": "warning",
                        "message": f"Cannot retrieve build info: {e}",
                        "suggested_action": "Verify /api/status/buildinfo endpoint is accessible.",
                    })

                # 3. Service status
                services = None
                try:
                    services = await tempo_service.get_status_services(backend_id)
                    if services:
                        for component, status in services.items():
                            if isinstance(status, str) and status.lower() not in ("running", "ready", "new"):
                                if overall_status == "healthy":
                                    overall_status = "degraded"
                                findings.append({
                                    "category": "health",
                                    "severity": "warning",
                                    "message": f"Component '{component}' status: {status}",
                                    "suggested_action": f"Check {component} logs for issues.",
                                })
                except Exception:
                    pass

                # 4. Deployment mode + ring checks
                # B-03 (revised): Auto-detecting deployment mode by probing
                # /status/services or /distributor/ring is unreliable — in
                # distributed setups the MCP server hits the query-frontend
                # (or gateway), which only reports that pod's internal services.
                # Ring checks are only meaningful when deployment_mode is
                # explicitly configured via TEMPO_DEPLOYMENT_MODE.
                ring_checks = None
                detected_mode = "unknown"
                try:
                    backend = tempo_service._get_backend(backend_id)
                    detected_mode = backend.deployment_mode
                except Exception:
                    pass

                if detected_mode == "unknown":
                    # Don't probe ring endpoints — we'd get false positives.
                    findings.append({
                        "category": "configuration",
                        "severity": "info",
                        "message": (
                            "Deployment mode is not configured. Ring health "
                            "checks are skipped to avoid false-positive "
                            "degraded findings from ring endpoint 404s."
                        ),
                        "suggested_action": (
                            "Set TEMPO_DEPLOYMENT_MODE='microservices' or "
                            "'monolithic' to enable ring diagnostics."
                        ),
                    })
                else:
                    # Mode is explicitly set — safe to probe rings.
                    try:
                        ring_checks = await tempo_service.check_rings(
                            backend_id,
                            deployment_mode_override=detected_mode,
                        )
                        for ring_name, ring_status in ring_checks.items():
                            if not isinstance(ring_status, dict):
                                continue
                            if ring_status.get("status") == "error":
                                if overall_status == "healthy":
                                    overall_status = "degraded"
                                findings.append({
                                    "category": "performance",
                                    "severity": "warning",
                                    "message": f"Ring '{ring_name}' check failed: {ring_status.get('error', '')}",
                                    "suggested_action": f"Review {ring_name} member health and replication.",
                                })
                    except Exception:
                        pass

                # 6. Positive findings
                if is_ready and not findings:
                    findings.append({
                        "category": "health",
                        "severity": "info",
                        "message": "All health checks passed.",
                        "suggested_action": None,
                    })

                issues = sum(1 for f in findings if f["severity"] in ("error", "critical", "warning"))

                return {
                    "status": overall_status,
                    "ready": is_ready,
                    "deployment_mode": detected_mode,
                    "build_info": build_info,
                    "services": services,
                    "ring_checks": ring_checks,
                    "findings": findings,
                    "issues": issues,
                }
            except Exception as e:
                raise TempoOperationError(f"Diagnostics failed: {e}")
