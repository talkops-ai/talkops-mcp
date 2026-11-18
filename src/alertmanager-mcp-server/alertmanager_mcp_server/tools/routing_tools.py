"""Routing tree simulation, notification pipeline health, and test alert tools (`routing` toolset)."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, Dict, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from alertmanager_mcp_server.domain.timeparse import (
    TimeValidationError,
    format_rfc3339_utc,
    parse_rfc3339,
    utc_now,
)
from alertmanager_mcp_server.exceptions import AlertmanagerValidationError
from alertmanager_mcp_server.models.responses import (
    NotificationHealthResponse,
    PushTestAlertResponse,
    RoutingExplanationResponse,
)
from alertmanager_mcp_server.tools._confirmation import (
    confirm_or_elicit,
    ensure_write_allowed,
    safe_ctx_info,
)
from alertmanager_mcp_server.tools.base import BaseTool
from alertmanager_mcp_server.utils.audit import add_audit_entry


class RoutingTools(BaseTool):
    """Tools for notification health verification, routing tree simulation, and test alert delivery."""

    def register(self, mcp_instance: object) -> None:
        if not self.config.is_toolset_enabled("routing"):
            return

        mcp: Any = mcp_instance

        @mcp.tool(
            annotations=ToolAnnotations(
                title="Check Notification Pipeline Health",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_check_notification_health(
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            integration: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description=(
                        "Optional receiver integration type filter (e.g. 'slack', "
                        "'pagerduty', 'email', 'webhook', 'opsgenie')"
                    ),
                ),
            ] = None,
            ctx: Optional[Context] = None,
        ) -> NotificationHealthResponse:
            """Inspect Alertmanager readiness, config reload status, cluster peers, and `/metrics` receiver delivery failure counters."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(
                ctx, f"Checking notification delivery health on backend '{bid}'"
            )

            report = await self.alertmanager_service.check_notification_health(
                bid, integration=integration
            )
            return NotificationHealthResponse(**report)

        @mcp.tool(
            annotations=ToolAnnotations(
                title="Explain Alert Routing & Inhibition",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_explain_routing(
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            labels: Annotated[
                Optional[Dict[str, str]],
                Field(
                    default=None,
                    description="Alert label set to evaluate (e.g. {'alertname': 'HighErrorRate', 'env': 'prod', 'severity': 'critical'})",
                ),
            ] = None,
            fingerprint: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Optional live alert fingerprint (auto-loads labels from the live alert)",
                ),
            ] = None,
            at_time: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Optional RFC3339 timestamp with timezone offset to evaluate mute_time_intervals / active_time_intervals at",
                ),
            ] = None,
            check_live_state: Annotated[
                bool,
                Field(
                    default=True,
                    description="Whether to evaluate live active silences and currently firing source alerts for inhibition rules",
                ),
            ] = True,
            ctx: Optional[Context] = None,
        ) -> RoutingExplanationResponse:
            """Simulate Alertmanager's nested routing tree (`continue`, inherited `group_by`/timers, `mute_time_intervals`) and live inhibition rules."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(ctx, f"Explaining routing on backend '{bid}'")

            eval_dt = None
            if at_time:
                try:
                    eval_dt = parse_rfc3339(
                        at_time, require_tz=True, field_name="at_time"
                    )
                except TimeValidationError as exc:
                    raise AlertmanagerValidationError(str(exc)) from exc

            result = await self.alertmanager_service.explain_routing_detailed(
                bid,
                alert_labels=labels,
                fingerprint=fingerprint,
                at_time=eval_dt,
                check_live_state=check_live_state,
            )
            return RoutingExplanationResponse(**result)

        if self.config.allow_write:

            @mcp.tool(
                annotations=ToolAnnotations(
                    title="Push Synthetic Test Alert",
                    readOnlyHint=False,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=True,
                )
            )
            async def am_push_test_alert(
                labels: Annotated[
                    Dict[str, str],
                    Field(
                        description=(
                            "Alert labels dictionary (MUST include 'alertname', e.g. "
                            "{'alertname': 'MCPPipelineTest', 'service': 'checkout', 'severity': 'warning'})"
                        )
                    ),
                ],
                backend_id: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Alertmanager backend ID (defaults to primary backend)",
                    ),
                ] = None,
                annotations: Annotated[
                    Optional[Dict[str, str]],
                    Field(
                        default=None,
                        description="Optional alert annotations (e.g. {'summary': 'Synthetic pipeline test'})",
                    ),
                ] = None,
                resolve_after_minutes: Annotated[
                    int,
                    Field(
                        default=5,
                        ge=1,
                        le=60,
                        description="Minutes until the synthetic test alert automatically resolves (1..60)",
                    ),
                ] = 5,
                generator_url: Annotated[
                    Optional[str],
                    Field(
                        default=None,
                        description="Optional generatorURL metadata on the synthetic alert",
                    ),
                ] = None,
                confirm: Annotated[
                    bool,
                    Field(
                        default=False,
                        description="Set True to confirm firing a live test alert to matched receivers",
                    ),
                ] = False,
                ctx: Optional[Context] = None,
            ) -> PushTestAlertResponse:
                """Push a time-bounded synthetic test alert to Alertmanager to verify end-to-end receiver delivery."""
                bid = self.alertmanager_service.resolve_backend_id(backend_id)
                ensure_write_allowed(
                    self.config,
                    backend_id=bid,
                    operation="push_test_alert",
                    principal="operator",
                )

                if not isinstance(labels, dict) or not labels.get("alertname"):
                    raise AlertmanagerValidationError(
                        "labels must be a dictionary containing a non-empty 'alertname' key."
                    )

                final_labels = {str(k): str(v) for k, v in labels.items()}
                test_marker = self.config.test_alert_label
                if test_marker and test_marker not in final_labels:
                    final_labels[test_marker] = "true"

                final_annotations = dict(
                    annotations
                    or {
                        "summary": f"Synthetic Alertmanager pipeline test ({final_labels['alertname']})",
                    }
                )

                routing_preview = (
                    await self.alertmanager_service.explain_routing_detailed(
                        bid,
                        alert_labels=final_labels,
                        check_live_state=True,
                    )
                )
                receivers = routing_preview.get("receivers") or []

                await confirm_or_elicit(
                    ctx,
                    confirm=confirm,
                    prompt_message=(
                        f"Pushing synthetic test alert '{final_labels['alertname']}' to backend "
                        f"'{bid}' will trigger real notifications to receiver(s): "
                        f"{', '.join(receivers) or 'default'} (auto-resolves in "
                        f"{resolve_after_minutes}m)."
                    ),
                    backend_id=bid,
                    operation="push_test_alert",
                    principal="operator",
                    audit_log_path=self.config.audit_log_path,
                    details={
                        "labels": final_labels,
                        "receivers": receivers,
                    },
                )

                now = utc_now()
                end_dt = now + timedelta(minutes=resolve_after_minutes)
                starts_str = format_rfc3339_utc(now)
                ends_str = format_rfc3339_utc(end_dt)

                alert_payload = {
                    "labels": final_labels,
                    "annotations": final_annotations,
                    "startsAt": starts_str,
                    "endsAt": ends_str,
                }
                if generator_url:
                    alert_payload["generatorURL"] = generator_url

                await self.alertmanager_service.push_alerts(bid, [alert_payload])
                add_audit_entry(
                    backend_id=bid,
                    operation="push_test_alert",
                    principal="operator",
                    summary=(
                        f"alertname={final_labels['alertname']} receivers={receivers} "
                        f"resolve_after={resolve_after_minutes}m"
                    ),
                    outcome="succeeded",
                    details={
                        "labels": final_labels,
                        "receivers": receivers,
                        "starts_at": starts_str,
                        "ends_at": ends_str,
                    },
                    audit_log_path=self.config.audit_log_path,
                )

                return PushTestAlertResponse(
                    backend_id=bid,
                    status="sent",
                    alertname=final_labels["alertname"],
                    labels=final_labels,
                    annotations=final_annotations,
                    starts_at=starts_str,
                    ends_at=ends_str,
                    resolve_after_minutes=resolve_after_minutes,
                    routing_preview={
                        "matched_route": routing_preview["matched_route"],
                        "receivers": receivers,
                        "active_receivers": routing_preview["active_receivers"],
                        "muted_receivers": routing_preview["muted_receivers"],
                        "is_inhibited": routing_preview["is_inhibited"],
                    },
                    message=(
                        f"Synthetic test alert '{final_labels['alertname']}' pushed to '{bid}' "
                        f"(routed to {', '.join(receivers) or 'default'}, auto-resolves at {ends_str})."
                    ),
                )
