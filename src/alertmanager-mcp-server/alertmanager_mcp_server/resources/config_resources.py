"""Config and receiver resources."""
import json
from alertmanager_mcp_server.resources.base import BaseResource


class ConfigResources(BaseResource):
    def register(self, mcp_instance) -> None:
        @mcp_instance.resource("am://system/receivers", name="am_receivers",
                               description="Configured receivers (Slack, PagerDuty, email, webhook) with redacted config",
                               mime_type="application/json")
        async def receivers_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            default = next((b for b in backends if b.is_default), backends[0] if backends else None)
            if not default:
                return json.dumps({"receivers": []})
            receivers = await self.alertmanager_service.get_receivers(default.id)
            return json.dumps({"receivers": [r.model_dump() for r in receivers]}, default=str, indent=2)

        @mcp_instance.resource("am://system/config", name="am_config",
                               description="Routing tree and inhibition rules (secrets redacted)",
                               mime_type="application/json")
        async def config_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            default = next((b for b in backends if b.is_default), backends[0] if backends else None)
            if not default:
                return json.dumps({"routes": [], "inhibitions": []})
            snapshot = await self.alertmanager_service.get_config_snapshot(default.id)
            return json.dumps(snapshot.model_dump(), default=str, indent=2)
