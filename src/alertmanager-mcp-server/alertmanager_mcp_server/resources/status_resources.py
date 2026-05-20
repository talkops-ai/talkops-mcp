"""System status resources."""
import json
from alertmanager_mcp_server.resources.base import BaseResource


class StatusResources(BaseResource):
    def register(self, mcp_instance) -> None:
        @mcp_instance.resource("am://system/status", name="am_status",
                               description="Alertmanager version, uptime, cluster info, and config summary",
                               mime_type="application/json")
        async def status_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            default = next((b for b in backends if b.is_default), backends[0] if backends else None)
            if not default:
                return json.dumps({"error": "No backends configured"})
            status = await self.alertmanager_service.get_status(default.id)
            # Extract key fields for LLM-friendly snapshot
            version_info = status.get("versionInfo", {})
            return json.dumps({
                "version": version_info.get("version"),
                "revision": version_info.get("revision"),
                "build_date": version_info.get("buildDate"),
                "uptime": status.get("uptime"),
                "cluster": status.get("cluster", {}),
            }, default=str, indent=2)
