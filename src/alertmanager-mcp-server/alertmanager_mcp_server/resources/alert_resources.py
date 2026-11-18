"""Backend-scoped alert snapshot and single-alert detail resources."""

from __future__ import annotations

import json
from typing import Any

from alertmanager_mcp_server.resources.base import BaseResource


class AlertResources(BaseResource):
    def register(self, mcp_instance: Any) -> None:
        @mcp_instance.resource(
            "am://backends/{backend_id}/alerts/active",
            name="am_backend_active_alerts",
            description="Bounded snapshot of active firing alerts for a specific Alertmanager backend",
            mime_type="application/json",
        )
        async def active_alerts_resource(backend_id: str) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            alerts, total, has_more, _ = (
                await self.alertmanager_service.list_alerts_with_total(
                    bid,
                    active=True,
                    silenced=False,
                    inhibited=False,
                    limit=50,
                    offset=0,
                )
            )
            return json.dumps(
                {
                    "backend_id": bid,
                    "total": total,
                    "has_more": has_more,
                    "alerts": [a.model_dump(mode="json") for a in alerts],
                },
                default=str,
                indent=2,
            )

        @mcp_instance.resource(
            "am://backends/{backend_id}/alerts/groups",
            name="am_backend_alert_groups",
            description="Snapshot of Alertmanager dispatch groups for a specific backend",
            mime_type="application/json",
        )
        async def alert_groups_resource(backend_id: str) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            groups = await self.alertmanager_service.list_alert_groups(bid)
            return json.dumps(
                {
                    "backend_id": bid,
                    "total_groups": len(groups),
                    "groups": [g.model_dump(mode="json") for g in groups],
                },
                default=str,
                indent=2,
            )

        @mcp_instance.resource(
            "am://backends/{backend_id}/alerts/{fingerprint}",
            name="am_backend_alert_detail",
            description="Full labels, annotations, receivers, and status for a specific alert fingerprint on a backend",
            mime_type="application/json",
        )
        async def alert_detail_resource(
            backend_id: str, fingerprint: str
        ) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            alert = await self.alertmanager_service.get_alert_by_fingerprint(
                bid, fingerprint
            )
            return json.dumps(
                {
                    "backend_id": bid,
                    "alert": alert.model_dump(mode="json"),
                },
                default=str,
                indent=2,
            )
