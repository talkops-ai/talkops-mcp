"""Alert resources."""
import json
from alertmanager_mcp_server.resources.base import BaseResource


class AlertResources(BaseResource):
    def register(self, mcp_instance) -> None:
        @mcp_instance.resource("am://alerts/active", name="am_active_alerts",
                               description="Bounded snapshot of active alerts for default backend", mime_type="application/json")
        async def active_alerts_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            default = next((b for b in backends if b.is_default), backends[0] if backends else None)
            if not default:
                return json.dumps({"alerts": [], "error": "No backends configured"})
            alerts, _, _ = await self.alertmanager_service.list_alerts(
                default.id, active=True, silenced=False, inhibited=False, limit=50, offset=0,
            )
            return json.dumps({"alerts": [a.model_dump(mode="json") for a in alerts]}, default=str, indent=2)

        @mcp_instance.resource("am://alerts/groups", name="am_alert_groups",
                               description="Snapshot of alert groups as computed by Alertmanager", mime_type="application/json")
        async def alert_groups_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            default = next((b for b in backends if b.is_default), backends[0] if backends else None)
            if not default:
                return json.dumps({"groups": [], "error": "No backends configured"})
            groups = await self.alertmanager_service.list_alert_groups(default.id)
            return json.dumps({"groups": [g.model_dump(mode="json") for g in groups]}, default=str, indent=2)
