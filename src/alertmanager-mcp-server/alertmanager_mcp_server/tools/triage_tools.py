"""On-call triage and alert querying tools (`triage` toolset)."""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from alertmanager_mcp_server.domain.matchers import (
    MatcherValidationError,
    parse_matcher_set,
)
from alertmanager_mcp_server.exceptions import AlertmanagerValidationError
from alertmanager_mcp_server.models.alert import AlertMatcher
from alertmanager_mcp_server.models.responses import (
    AlertGroupsResponse,
    AlertListResponse,
    OncallSummaryResponse,
)
from alertmanager_mcp_server.tools._confirmation import safe_ctx_info
from alertmanager_mcp_server.tools.base import BaseTool

AlertStateFilter = Literal[
    "active", "suppressed", "silenced", "inhibited", "unprocessed", "all"
]
GroupStateFilter = Literal["active", "suppressed", "all"]


class TriageTools(BaseTool):
    """Read-only tools for on-call alert summarization, querying, and grouping."""

    def register(self, mcp_instance: Any) -> None:
        if not self.config.is_toolset_enabled("triage"):
            return

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
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            env: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Filter by environment label (e.g. prod, staging)",
                ),
            ] = None,
            service: Annotated[
                Optional[str],
                Field(default=None, description="Filter by service label"),
            ] = None,
            team: Annotated[
                Optional[str],
                Field(default=None, description="Filter by owning team label"),
            ] = None,
            severity: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Filter by severity label (e.g. critical, warning)",
                ),
            ] = None,
            ctx: Optional[Context] = None,
        ) -> OncallSummaryResponse:
            """Generate a structured on-call triage summary of active and suppressed alerts.

            Aggregates firing alerts by severity, environment, service, and team,
            verifies dead-man's-switch (Watchdog) heartbeat status, and reports
            active silence count.
            """
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(ctx, f"Generating on-call summary for backend '{bid}'")

            matchers: List[AlertMatcher] = []
            if env:
                matchers.append(
                    AlertMatcher(
                        name=self.config.label_env,
                        value=env,
                        isRegex=False,
                        isEqual=True,
                    )
                )
            if service:
                matchers.append(
                    AlertMatcher(
                        name=self.config.label_service,
                        value=service,
                        isRegex=False,
                        isEqual=True,
                    )
                )
            if team:
                matchers.append(
                    AlertMatcher(
                        name=self.config.label_team,
                        value=team,
                        isRegex=False,
                        isEqual=True,
                    )
                )
            if severity:
                matchers.append(
                    AlertMatcher(
                        name=self.config.label_severity,
                        value=severity,
                        isRegex=False,
                        isEqual=True,
                    )
                )

            all_alerts, _, _ = await self.alertmanager_service.list_alerts(
                bid,
                matchers=matchers or None,
                active=True,
                silenced=True,
                inhibited=True,
                limit=1000,
                offset=0,
            )

            active_silences_count = 0
            try:
                _, active_silences_count, _, _ = (
                    await self.alertmanager_service.list_silences_with_total(
                        bid, state="active", limit=1, offset=0
                    )
                )
            except Exception:
                pass

            watchdog_name = self.config.watchdog_alertname.lower()
            watchdog_status = "missing"
            active_alerts = []
            suppressed_count = 0

            for alert in all_alerts:
                aname = alert.labels.get("alertname", "")
                st = (alert.status or {}).get("state", "active")
                if aname.lower() == watchdog_name:
                    watchdog_status = "firing" if st == "active" else "suppressed"
                    continue
                if st == "active":
                    active_alerts.append(alert)
                else:
                    suppressed_count += 1

            if not active_alerts:
                summary = (
                    f"All clear on '{bid}' — 0 active alerts firing "
                    f"({suppressed_count} suppressed, {active_silences_count} active silence(s), "
                    f"Watchdog: {watchdog_status})."
                )
                return OncallSummaryResponse(
                    backend_id=bid,
                    total_active_alerts=0,
                    total_suppressed_alerts=suppressed_count,
                    watchdog_status=watchdog_status,
                    active_silences_count=active_silences_count,
                    summary_text=summary,
                )

            sev_key = self.config.label_severity
            env_key = self.config.label_env
            svc_key = self.config.label_service
            team_key = self.config.label_team

            by_severity: Counter[str] = Counter()
            by_env: Counter[str] = Counter()
            by_service: Counter[str] = Counter()
            by_team: Counter[str] = Counter()
            by_alertname: Counter[str] = Counter()
            group_map: Dict[str, Dict[str, Any]] = {}

            for a in active_alerts:
                sev = a.labels.get(sev_key, "unknown")
                ev = a.labels.get(env_key, "unknown")
                svc = a.labels.get(svc_key, "unknown")
                tm = a.labels.get(team_key, "unassigned")
                aname = a.labels.get("alertname", "unknown")

                by_severity[sev] += 1
                by_env[ev] += 1
                by_service[svc] += 1
                by_team[tm] += 1
                by_alertname[aname] += 1

                gkey = f"{svc}/{aname}"
                if gkey not in group_map:
                    group_map[gkey] = {
                        "service": svc,
                        "alertname": aname,
                        "severity": sev,
                        "env": ev,
                        "count": 0,
                        "sample_fingerprint": a.fingerprint,
                    }
                group_map[gkey]["count"] += 1

            top_groups = sorted(
                group_map.values(), key=lambda g: g["count"], reverse=True
            )[:10]

            lines = [
                f"On-Call Triage Summary ({bid}): {len(active_alerts)} active alert(s), "
                f"{suppressed_count} suppressed, {active_silences_count} active silence(s). "
                f"Watchdog: {watchdog_status}."
            ]
            sev_parts = [f"{k}={v}" for k, v in by_severity.most_common()]
            if sev_parts:
                lines.append(f"By severity: {', '.join(sev_parts)}.")
            svc_parts = [f"{k} ({v})" for k, v in by_service.most_common(5)]
            if svc_parts:
                lines.append(f"Top affected services: {', '.join(svc_parts)}.")

            return OncallSummaryResponse(
                backend_id=bid,
                total_active_alerts=len(active_alerts),
                total_suppressed_alerts=suppressed_count,
                by_severity=dict(by_severity),
                by_env=dict(by_env),
                by_service=dict(by_service),
                by_team=dict(by_team),
                top_alertnames=dict(by_alertname.most_common(10)),
                top_alert_groups=top_groups,
                watchdog_status=watchdog_status,
                active_silences_count=active_silences_count,
                summary_text=" ".join(lines),
            )

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
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            alertname: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertname filter (supports exact name or '=~regex')",
                ),
            ] = None,
            severity: Annotated[
                Optional[str],
                Field(default=None, description="Severity label filter"),
            ] = None,
            label_filters: Annotated[
                Optional[Dict[str, str] | List[str] | str],
                Field(
                    default=None,
                    description=(
                        "Additional label matchers as a dict (e.g. {'env': 'prod', 'service': '=~api|web'}), "
                        "list of matcher strings (['env=\"prod\"']), or braced selector ('{env=\"prod\"}')"
                    ),
                ),
            ] = None,
            receiver: Annotated[
                Optional[str],
                Field(default=None, description="Filter by receiver name regex"),
            ] = None,
            state: Annotated[
                AlertStateFilter,
                Field(
                    default="active",
                    description="Alert state filter: active, suppressed, silenced, inhibited, unprocessed, or all",
                ),
            ] = "active",
            limit: Annotated[
                int,
                Field(
                    default=50,
                    ge=1,
                    le=500,
                    description="Maximum alerts to return per page (1..500)",
                ),
            ] = 50,
            offset: Annotated[
                int,
                Field(default=0, ge=0, description="Pagination offset"),
            ] = 0,
            ctx: Optional[Context] = None,
        ) -> AlertListResponse:
            """Query alerts from Alertmanager with full matcher grammar and state filtering."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(ctx, f"Listing alerts on backend '{bid}' (state={state})")

            matchers: List[AlertMatcher] = []
            if alertname:
                if alertname.startswith(("=~", "!~", "!=")):
                    op = alertname[:2]
                    matchers.append(
                        AlertMatcher(
                            name="alertname",
                            value=alertname[2:].strip().strip('"'),
                            isRegex=op in ("=~", "!~"),
                            isEqual=op in ("=", "=~"),
                        )
                    )
                else:
                    matchers.append(
                        AlertMatcher(
                            name="alertname",
                            value=alertname,
                            isRegex=False,
                            isEqual=True,
                        )
                    )

            if severity:
                matchers.append(
                    AlertMatcher(
                        name=self.config.label_severity,
                        value=severity,
                        isRegex=False,
                        isEqual=True,
                    )
                )

            if label_filters is not None:
                try:
                    compiled = parse_matcher_set(label_filters)
                    for m in compiled:
                        matchers.append(
                            AlertMatcher(
                                name=m.name,
                                value=m.value,
                                isRegex=m.is_regex,
                                isEqual=m.is_equal,
                            )
                        )
                except MatcherValidationError as exc:
                    raise AlertmanagerValidationError(
                        f"Invalid label_filters: {exc}"
                    ) from exc

            active_flag: Optional[bool] = True
            silenced_flag: Optional[bool] = False
            inhibited_flag: Optional[bool] = False
            unprocessed_flag: Optional[bool] = False

            if state == "active":
                active_flag, silenced_flag, inhibited_flag, unprocessed_flag = (
                    True,
                    False,
                    False,
                    False,
                )
            elif state == "suppressed":
                active_flag, silenced_flag, inhibited_flag, unprocessed_flag = (
                    False,
                    True,
                    True,
                    False,
                )
            elif state == "silenced":
                active_flag, silenced_flag, inhibited_flag, unprocessed_flag = (
                    False,
                    True,
                    False,
                    False,
                )
            elif state == "inhibited":
                active_flag, silenced_flag, inhibited_flag, unprocessed_flag = (
                    False,
                    False,
                    True,
                    False,
                )
            elif state == "unprocessed":
                active_flag, silenced_flag, inhibited_flag, unprocessed_flag = (
                    False,
                    False,
                    False,
                    True,
                )
            elif state == "all":
                active_flag, silenced_flag, inhibited_flag, unprocessed_flag = (
                    True,
                    True,
                    True,
                    True,
                )

            alerts, total, has_more, _ = (
                await self.alertmanager_service.list_alerts_with_total(
                    bid,
                    matchers=matchers or None,
                    active=active_flag,
                    silenced=silenced_flag,
                    inhibited=inhibited_flag,
                    unprocessed=unprocessed_flag,
                    receiver=receiver,
                    limit=limit,
                    offset=offset,
                )
            )
            return AlertListResponse(
                backend_id=bid,
                total=total,
                offset=offset,
                limit=limit,
                has_more=has_more,
                alerts=[a.model_dump(mode="json") for a in alerts],
            )

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
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            receiver: Annotated[
                Optional[str],
                Field(default=None, description="Filter groups by receiver name"),
            ] = None,
            state: Annotated[
                GroupStateFilter,
                Field(
                    default="active",
                    description="Filter alerts in groups by state: active, suppressed, or all",
                ),
            ] = "active",
            max_alerts_per_group: Annotated[
                int,
                Field(
                    default=20,
                    ge=1,
                    le=100,
                    description="Maximum alerts included per group (1..100)",
                ),
            ] = 20,
            limit: Annotated[
                int,
                Field(
                    default=50,
                    ge=1,
                    le=200,
                    description="Maximum groups to return per page (1..200)",
                ),
            ] = 50,
            offset: Annotated[
                int,
                Field(default=0, ge=0, description="Pagination offset"),
            ] = 0,
            ctx: Optional[Context] = None,
        ) -> AlertGroupsResponse:
            """List Alertmanager dispatch groups grouped by route `group_by` labels."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(ctx, f"Listing alert groups on backend '{bid}'")

            active_flag: Optional[bool] = None
            silenced_flag: Optional[bool] = None
            inhibited_flag: Optional[bool] = None
            if state == "active":
                active_flag, silenced_flag, inhibited_flag = True, False, False
            elif state == "suppressed":
                active_flag, silenced_flag, inhibited_flag = False, True, True

            groups = await self.alertmanager_service.list_alert_groups(
                bid,
                max_alerts_per_group=max_alerts_per_group,
                active=active_flag,
                silenced=silenced_flag,
                inhibited=inhibited_flag,
                receiver=receiver,
            )
            total = len(groups)
            page = groups[offset : offset + limit]
            has_more = offset + limit < total
            return AlertGroupsResponse(
                backend_id=bid,
                total_groups=total,
                offset=offset,
                limit=limit,
                has_more=has_more,
                groups=[g.model_dump(mode="json") for g in page],
            )
