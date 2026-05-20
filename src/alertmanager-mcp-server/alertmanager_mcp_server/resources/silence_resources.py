"""Silence resources."""
import json
from alertmanager_mcp_server.resources.base import BaseResource


class SilenceResources(BaseResource):
    def register(self, mcp_instance) -> None:
        @mcp_instance.resource("am://silences/active", name="am_active_silences",
                               description="Snapshot of active silences for default backend", mime_type="application/json")
        async def active_silences_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            default = next((b for b in backends if b.is_default), backends[0] if backends else None)
            if not default:
                return json.dumps({"silences": []})
            silences, _, _ = await self.alertmanager_service.list_silences(default.id, state="active")
            return json.dumps({"silences": [s.model_dump(mode="json") for s in silences]}, default=str, indent=2)
