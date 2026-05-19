"""Backend resources."""
import json
from alertmanager_mcp_server.models.backend import BackendDescriptor
from alertmanager_mcp_server.resources.base import BaseResource


class BackendResources(BaseResource):
    def register(self, mcp_instance) -> None:
        @mcp_instance.resource("am://system/backends", name="am_backends",
                               description="All Alertmanager backends with health status", mime_type="application/json")
        async def list_backends_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            result = []
            for b in backends:
                health = await self.alertmanager_service.check_health(b.id)
                updated = BackendDescriptor(
                    id=b.id, display_name=b.display_name,
                    base_url=b.base_url, labels=b.labels,
                    health=health, version=b.version, is_default=b.is_default,
                )
                result.append(updated.model_dump())
            return json.dumps({"backends": result}, default=str, indent=2)

        @mcp_instance.resource("am://system/backends/{backend_id}", name="am_backend_detail",
                               description="Detailed status, version, cluster info, and health for one backend",
                               mime_type="application/json")
        async def get_backend_detail_resource(backend_id: str) -> str:
            health = await self.alertmanager_service.check_health(backend_id)
            status = await self.alertmanager_service.get_status(backend_id)
            backends = self.alertmanager_service.list_backends()
            backend = next((b for b in backends if b.id == backend_id), None)
            if not backend:
                return json.dumps({"error": f"Unknown backend_id '{backend_id}'"})
            version_info = status.get("versionInfo", {})
            return json.dumps({
                "backend": {
                    "id": backend.id,
                    "display_name": backend.display_name,
                    "base_url": backend.base_url,
                    "labels": backend.labels,
                    "health": health,
                    "is_default": backend.is_default,
                    "version": version_info.get("version"),
                    "revision": version_info.get("revision"),
                    "build_date": version_info.get("buildDate"),
                },
                "cluster": status.get("cluster", {}),
                "uptime": status.get("uptime"),
            }, default=str, indent=2)
