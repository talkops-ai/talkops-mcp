"""High-level helper workflow tools — granular pattern."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.models.silence import PostableSilence
from alertmanager_mcp_server.utils import all_matchers_match, compute_silence_window, derive_matchers_from_labels
from alertmanager_mcp_server.utils.audit import add_audit_entry
from alertmanager_mcp_server.tools.base import BaseTool


class HelperTools(BaseTool):
    """High-level helper workflows for silence previewing and quick alert silencing."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Preview Silence Effect",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_preview_silence(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            matchers: Annotated[List[Dict[str, Any]], Field(description="Matchers to simulate: [{name, value, isRegex, isEqual}]")],
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Preview the blast radius of a silence before creating it.

            Use this as a MANDATORY dry-run before creating broad silences. Shows
            how many and which alerts would be affected. Read-only.

            Returns:
            - {\"affected_alert_count\": int, \"affected_alerts_preview\": [{...}],
               \"would_affect_receivers\": [str], \"summary_text\": str, \"warning_flag\": bool}

            When NOT to use: For actually creating silences, use am_create_silence
            or am_silence_alert after previewing.
            """
            await ctx.info("Previewing silence effect")
            try:
                parsed = [AlertMatcher(**m) for m in matchers]
                alerts, _, _ = await self.alertmanager_service.list_alerts(
                    backend_id, active=True, limit=1000, offset=0,
                )
                affected = [a for a in alerts if all_matchers_match(a.labels, parsed)]
                threshold = self.config.silence_warning_threshold

                # Determine which receivers would be impacted
                affected_receivers: List[str] = []
                try:
                    for alert in affected:
                        result = await self.alertmanager_service.simulate_routing(backend_id, alert.labels)
                        for r in result.receivers:
                            if r not in affected_receivers:
                                affected_receivers.append(r)
                except Exception:
                    pass  # Best-effort enrichment

                # Build summary text
                matchers_str = ", ".join(f"{m.name}={m.value}" for m in parsed)
                if not affected:
                    summary = f"No active alerts match [{matchers_str}]. Safe to create."
                else:
                    summary = (
                        f"Silencing [{matchers_str}] would suppress {len(affected)} alert(s)."
                    )
                    if affected_receivers:
                        summary += f" Affected receivers: {', '.join(affected_receivers)}."
                    if len(affected) >= threshold:
                        summary += f" ⚠️ WARNING: This exceeds the {threshold}-alert threshold."

                return {
                    "affected_alert_count": len(affected),
                    "affected_alerts_preview": [a.model_dump(mode="json") for a in affected[:20]],
                    "would_affect_receivers": affected_receivers,
                    "summary_text": summary,
                    "warning_flag": len(affected) >= threshold,
                }
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Silence Alert",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def am_silence_alert(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            alert_fingerprint: Annotated[Optional[str], Field(description="Alert fingerprint to silence")] = None,
            alert_labels: Annotated[Optional[Any], Field(description="Alert labels to derive matchers from (must be a JSON object/dictionary)")] = None,
            scope: Annotated[Optional[str], Field(description="Matcher scope: instance (all labels), service (alertname+service+env), or env (env only)")] = "service",
            duration_minutes: Annotated[Optional[int], Field(description="Silence duration in minutes")] = 60,
            created_by: Annotated[Optional[str], Field(description="Creator identity")] = "mcp",
            comment: Annotated[Optional[str], Field(description="Justification comment")] = "Silence via Alertmanager MCP",
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Create a narrowly-scoped silence for a specific alert.

            LLM-friendly helper that derives matchers from an alert's fingerprint or
            labels. The 'scope' parameter controls how broad the matchers are:
            - instance: uses all alert labels (narrowest)
            - service: uses alertname + service + env (default, recommended)
            - env: uses env label only (broadest)

            MUTATES STATE. Requires either 'alert_fingerprint' or 'alert_labels'.

            Returns:
            - {\"silence_id\": str, \"silence\": {...}, \"derived_matchers\": [{...}]}

            When NOT to use: For explicit matcher control or custom time windows,
            use am_create_silence instead.

            Common errors:
            - Alert not found: If using fingerprint, the alert must be currently active.
            - Duration cap exceeded: Cannot exceed the configured max (default 24h/1440m).
            """
            await ctx.info("Silencing alert")
            try:
                max_dur = self.config.max_silence_duration_minutes
                dur = duration_minutes or 60
                if dur > max_dur:
                    return {"error": f"Duration {dur}m exceeds {max_dur}m cap.", "isError": True}

                import json
                if isinstance(alert_labels, str):
                    alert_labels = json.loads(alert_labels)

                labels: Dict[str, str] = {}
                if alert_labels:
                    labels = alert_labels
                elif alert_fingerprint:
                    alerts, _, _ = await self.alertmanager_service.list_alerts(
                        backend_id, active=True, silenced=True, limit=1000, offset=0,
                    )
                    match = next((a for a in alerts if a.fingerprint == alert_fingerprint), None)
                    if not match:
                        return {"error": "Alert with given fingerprint not found.", "isError": True}
                    labels = match.labels
                else:
                    return {"error": "Either 'alert_fingerprint' or 'alert_labels' is required.", "isError": True}

                # Derive matchers based on scope
                scope_val = scope or "service"
                if scope_val == "instance":
                    priority_keys = tuple(labels.keys())
                elif scope_val == "env":
                    priority_keys = ("env",)
                else:  # "service" (default)
                    priority_keys = ("alertname", "service", "env")

                derived = derive_matchers_from_labels(labels, priority_keys=priority_keys)
                now = datetime.now(timezone.utc)
                start, end = compute_silence_window(dur, None, None, now)
                silence = PostableSilence(
                    matchers=derived, startsAt=start, endsAt=end,
                    createdBy=created_by or "mcp", comment=comment or "Silence via MCP helper",
                )
                created = await self.alertmanager_service.create_silence(backend_id, silence)
                add_audit_entry(
                    backend_id=backend_id, operation="silence_alert",
                    principal=created_by or "mcp",
                    summary=f"id={created.id} scope={scope_val} labels={list(labels.keys())}",
                )
                return {
                    "silence_id": created.id,
                    "silence": created.model_dump(mode="json"),
                    "derived_matchers": [m.model_dump() for m in derived],
                }
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}
