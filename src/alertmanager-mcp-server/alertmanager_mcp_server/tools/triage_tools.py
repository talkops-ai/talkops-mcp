"""On-call triage and alert summarization tools."""

from typing import Any, Optional, Annotated
from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations
from alertmanager_mcp_server.tools.base import BaseTool


class TriageTools(BaseTool):
    """Tools for on-call triage and alert summarization."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Summarize Alerts for On-Call",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_summarize_oncall(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            env: Annotated[Optional[str], Field(description="Filter by environment (e.g. prod, staging)")] = None,
            service: Annotated[Optional[str], Field(description="Filter by service name")] = None,
            severity: Annotated[Optional[str], Field(description="Filter by severity (e.g. critical, warning)")] = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Generate a human-readable on-call summary of active alerts.

            Produces a narrative grouped by severity, service, and team — designed
            for quick triage during on-call handoffs. Read-only.

            Returns:
            - {\"summary_text\": str, \"total_alerts\": int, \"by_severity\": {...},
               \"by_service\": {...}, \"top_groups\": [{...}]}

            When NOT to use: For raw alert data with full filtering, use am_list_alerts.
            """
            await ctx.info(f"Generating on-call summary for backend: {backend_id}")
            try:
                from alertmanager_mcp_server.models.alert import AlertMatcher

                matchers = []
                if env:
                    matchers.append(AlertMatcher(name="env", value=env, isRegex=False, isEqual=True))
                if service:
                    matchers.append(AlertMatcher(name="service", value=service, isRegex=False, isEqual=True))
                if severity:
                    matchers.append(AlertMatcher(name="severity", value=severity, isRegex=False, isEqual=True))

                alerts, _, _ = await self.alertmanager_service.list_alerts(
                    backend_id, matchers=matchers or None,
                    active=True, silenced=False, inhibited=False,
                    limit=500, offset=0,
                )

                if not alerts:
                    return {
                        "summary_text": "🟢 All clear — no active alerts firing.",
                        "total_alerts": 0,
                        "by_severity": {},
                        "by_service": {},
                        "top_groups": [],
                    }

                # Group by severity
                by_severity: dict[str, int] = {}
                for a in alerts:
                    sev = a.labels.get("severity", "unknown")
                    by_severity[sev] = by_severity.get(sev, 0) + 1

                # Group by service
                by_service: dict[str, int] = {}
                for a in alerts:
                    svc = a.labels.get("service", "unknown")
                    by_service[svc] = by_service.get(svc, 0) + 1

                # Top groups (service + alertname)
                group_counts: dict[str, dict[str, Any]] = {}
                for a in alerts:
                    key = f"{a.labels.get('service', '?')}/{a.labels.get('alertname', '?')}"
                    if key not in group_counts:
                        group_counts[key] = {"service": a.labels.get("service", "?"), "alertname": a.labels.get("alertname", "?"), "count": 0, "severity": a.labels.get("severity", "?")}
                    group_counts[key]["count"] += 1
                top_groups = sorted(group_counts.values(), key=lambda g: g["count"], reverse=True)[:10]

                # Build summary text
                lines = [f"🚨 **On-Call Summary** — {len(alerts)} active alert(s)"]
                lines.append("")

                # Severity breakdown
                if "critical" in by_severity:
                    lines.append(f"  🔴 Critical: {by_severity['critical']}")
                if "warning" in by_severity:
                    lines.append(f"  🟡 Warning: {by_severity['warning']}")
                for sev, count in sorted(by_severity.items()):
                    if sev not in ("critical", "warning"):
                        lines.append(f"  ⚪ {sev}: {count}")

                lines.append("")
                lines.append("**Top affected services:**")
                for svc, count in sorted(by_service.items(), key=lambda x: x[1], reverse=True)[:5]:
                    lines.append(f"  - {svc}: {count} alert(s)")

                if top_groups:
                    lines.append("")
                    lines.append("**Top alert groups:**")
                    for g in top_groups[:5]:
                        lines.append(f"  - [{g['severity']}] {g['service']}/{g['alertname']}: {g['count']}")

                return {
                    "summary_text": "\n".join(lines),
                    "total_alerts": len(alerts),
                    "by_severity": by_severity,
                    "by_service": by_service,
                    "top_groups": top_groups,
                }
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}
