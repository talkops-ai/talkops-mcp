"""Alert listing, inspection, and test alert tools — granular pattern."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Annotated
from pydantic import Field
from fastmcp import Context
from mcp.types import ToolAnnotations
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.tools.base import BaseTool
from alertmanager_mcp_server.utils.audit import add_audit_entry


class AlertTools(BaseTool):
    """Tools for alert listing, grouping, and test alert injection."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Alerts",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_list_alerts(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            alertname: Annotated[Optional[str], Field(description="Filter by alertname")] = None,
            severity: Annotated[Optional[str], Field(description="Filter by severity label")] = None,
            label_filters: Annotated[Optional[Any], Field(description="Additional label filters (must be a JSON object/dictionary, e.g. {\"env\": \"prod\"})")] = None,
            receiver: Annotated[Optional[str], Field(description="Filter by receiver name")] = None,
            state: Annotated[Optional[str], Field(description="Filter: active, suppressed, or any")] = None,
            include_silenced: Annotated[Optional[bool], Field(description="Include silenced alerts")] = True,
            include_inhibited: Annotated[Optional[bool], Field(description="Include inhibited alerts")] = False,
            limit: Annotated[Optional[int], Field(description="Max results per page (default 50)")] = 50,
            offset: Annotated[Optional[int], Field(description="Pagination offset")] = 0,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """List alerts with label/state filters and pagination.

            Use this to inspect the current alert state of an Alertmanager backend
            for on-call triage or investigation. Read-only.

            Returns:
            - {\"alerts\": [{...}], \"has_more\": bool, \"next_offset\": int|null}

            When NOT to use: For suppressing alerts, use am_create_silence or
            am_silence_alert instead. For routing questions, use am_explain_routing.

            Common errors:
            - Backend unreachable: Use am_list_backends to verify connectivity.
            """
            await ctx.info(f"Listing alerts for backend: {backend_id}")
            try:
                matchers: List[AlertMatcher] = []
                if alertname:
                    matchers.append(AlertMatcher(name="alertname", value=alertname, isRegex=False, isEqual=True))
                if severity:
                    matchers.append(AlertMatcher(name="severity", value=severity, isRegex=False, isEqual=True))
                if label_filters:
                    if isinstance(label_filters, str):
                        try:
                            label_filters = json.loads(label_filters)
                        except Exception:
                            pass
                    if isinstance(label_filters, dict):
                        for k, v in label_filters.items():
                            matchers.append(AlertMatcher(name=k, value=str(v), isRegex=False, isEqual=True))

                # Map state to active/silenced/inhibited booleans
                include_active = True
                silenced = include_silenced
                inhibited = include_inhibited
                if state == "suppressed":
                    include_active = False
                    silenced = True
                    inhibited = True
                elif state == "active":
                    silenced = False
                    inhibited = False
                elif state == "any":
                    silenced = True
                    inhibited = True

                alerts, has_more, next_offset = await self.alertmanager_service.list_alerts(
                    backend_id, matchers=matchers or None,
                    active=include_active, silenced=silenced,
                    inhibited=inhibited,
                    receiver=receiver, limit=limit or 50, offset=offset or 0,
                )
                return {"alerts": [a.model_dump(mode="json") for a in alerts], "has_more": has_more, "next_offset": next_offset}
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="List Alert Groups",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_list_alert_groups(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """List alert groups as computed by Alertmanager for high-level triage.

            Returns alerts grouped by the configured group_by labels (e.g. alertname,
            cluster, service). Read-only.

            Returns:
            - [{\"labels\": {...}, \"alerts\": [{...}]}, ...]

            When NOT to use: For flat alert listing with filters, use am_list_alerts.
            """
            await ctx.info(f"Listing alert groups for backend: {backend_id}")
            try:
                groups = await self.alertmanager_service.list_alert_groups(backend_id)
                return [g.model_dump(mode="json") for g in groups]
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}

        @mcp_instance.tool(
            annotations=ToolAnnotations(
                title="Push Test Alert",
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=True,
            )
        )
        async def am_push_test_alert(
            backend_id: Annotated[str, Field(min_length=1, description="Alertmanager backend ID")],
            alert_labels: Annotated[
                Any,
                Field(
                    description=(
                        "Alert labels (must be a JSON object/dictionary). "
                        "MUST include an 'alertname' key. "
                        'Example: {"alertname": "TalkOpsDown", "severity": "critical", "instance": "https://talkops.ai"}. '
                        "Do NOT pass a list. Do NOT nest under an 'alert_labels' key."
                    )
                ),
            ],
            annotations: Annotated[
                Optional[Any],
                Field(
                    description=(
                        "Alert annotations (must be a JSON object/dictionary). "
                        'Example: {"summary": "Endpoint down", "description": "Returning non-2xx"}. '
                        "Do NOT pass a list."
                    )
                ),
            ] = None,
            ctx: Context = None,  # type: ignore[assignment]
        ) -> Any:
            """Fire a synthetic test alert to verify notification integrations.

            Use this to validate that receivers (Slack, PagerDuty, email, etc.) are
            correctly configured and receiving alerts. MUTATES STATE.

            **WARNING: This fires a real alert into Alertmanager and may trigger
            downstream notification integrations.**

            Returns:
            - {\"status\": \"ok\", \"result\": {...}}

            Common errors:
            - Missing alertname: alert_labels must include an 'alertname' key.
            - Wrong type: alert_labels and annotations must be plain flat dicts
              (string → string) — NOT a list, NOT a dict nested under 'alert_labels'.
            """
            await ctx.info(f"Pushing test alert to backend: {backend_id}")
            try:
                import json
                if isinstance(alert_labels, str):
                    alert_labels = json.loads(alert_labels)
                if isinstance(annotations, str):
                    annotations = json.loads(annotations)
                    
                if not isinstance(alert_labels, dict):
                    return {"error": "alert_labels must be a JSON object/dictionary", "isError": True}
                    
                if "alertname" not in alert_labels:
                    return {"error": "alert_labels must include 'alertname'.", "isError": True}
                now = datetime.now(timezone.utc).isoformat()
                alert = {
                    "labels": alert_labels,
                    "annotations": annotations or {"summary": "Test alert from Alertmanager MCP"},
                    "startsAt": now,
                }
                result = await self.alertmanager_service.push_alerts(backend_id, [alert])
                add_audit_entry(
                    backend_id=backend_id, operation="push_test_alert",
                    principal="mcp", summary=f"alertname={alert_labels.get('alertname', '?')}",
                )
                return {"status": "ok", "result": result}
            except Exception as e:
                await ctx.error(str(e))
                return {"error": str(e), "isError": True}
