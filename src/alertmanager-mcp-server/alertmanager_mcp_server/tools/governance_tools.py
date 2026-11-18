"""Alert routing hygiene and silence governance audit tools (`governance` toolset)."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastmcp import Context
from mcp.types import ToolAnnotations
from pydantic import Field

from alertmanager_mcp_server.models.responses import (
    AlertHygieneAuditResponse,
    SilenceGovernanceAuditResponse,
)
from alertmanager_mcp_server.tools._confirmation import safe_ctx_info
from alertmanager_mcp_server.tools.base import BaseTool


class GovernanceTools(BaseTool):
    """Read-only tools for alert taxonomy/routing hygiene and silence governance audits."""

    def register(self, mcp_instance: object) -> None:
        if not self.config.is_toolset_enabled("governance"):
            return

        mcp: Any = mcp_instance

        @mcp.tool(
            annotations=ToolAnnotations(
                title="Audit Alert & Routing Hygiene",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_audit_alert_hygiene(
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            check_default_route: Annotated[
                bool,
                Field(
                    default=True,
                    description="Detect active alerts falling through to the root default receiver",
                ),
            ] = True,
            check_missing_annotations: Annotated[
                bool,
                Field(
                    default=True,
                    description="Detect alerts missing required annotations (e.g. summary, runbook_url)",
                ),
            ] = True,
            check_long_firing_hours: Annotated[
                int,
                Field(
                    default=24,
                    ge=1,
                    description="Threshold in hours to flag chronic long-firing alerts",
                ),
            ] = 24,
            limit: Annotated[
                int,
                Field(
                    default=50,
                    ge=1,
                    le=200,
                    description="Maximum sample alerts returned per hygiene finding category",
                ),
            ] = 50,
            ctx: Optional[Context] = None,
        ) -> AlertHygieneAuditResponse:
            """Audit active alerts for default-route leakage, missing runbook/summary annotations, invalid severity values, chronic long-firing alerts, and Watchdog heartbeat presence."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(ctx, f"Auditing alert hygiene on backend '{bid}'")

            report = await self.alertmanager_service.audit_alert_hygiene(
                bid,
                check_default_route=check_default_route,
                check_missing_annotations=check_missing_annotations,
                check_long_firing_hours=check_long_firing_hours,
                limit=limit,
            )
            return AlertHygieneAuditResponse(**report)

        @mcp.tool(
            annotations=ToolAnnotations(
                title="Audit Silences & Governance Compliance",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            )
        )
        async def am_audit_silences(
            backend_id: Annotated[
                Optional[str],
                Field(
                    default=None,
                    description="Alertmanager backend ID (defaults to primary backend)",
                ),
            ] = None,
            since_minutes: Annotated[
                int,
                Field(
                    default=1440,
                    ge=1,
                    description="Look-back window in minutes for created/updated/expired silence change history (default 1440 = 24h)",
                ),
            ] = 1440,
            expiring_within_minutes: Annotated[
                int,
                Field(
                    default=120,
                    ge=1,
                    description="Window in minutes to flag active silences that will expire soon",
                ),
            ] = 120,
            ctx: Optional[Context] = None,
        ) -> SilenceGovernanceAuditResponse:
            """Audit silence change history, active silence policy compliance (`SP001`–`SP009`), stale 0-match silences, and silences expiring soon."""
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            await safe_ctx_info(ctx, f"Auditing silence governance on backend '{bid}'")

            report = await self.alertmanager_service.audit_silences(
                bid,
                since_minutes=since_minutes,
                expiring_within_minutes=expiring_within_minutes,
            )
            return SilenceGovernanceAuditResponse(**report)
