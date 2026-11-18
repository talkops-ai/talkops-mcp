"""Backend discovery, status, configuration, and receiver resources (`am://backends/...`)."""

from __future__ import annotations

import json
from typing import Any

from alertmanager_mcp_server.domain.time_intervals import TimeIntervalCatalog
from alertmanager_mcp_server.models.backend import BackendDescriptor
from alertmanager_mcp_server.resources.base import BaseResource


class BackendResources(BaseResource):
    def register(self, mcp_instance: Any) -> None:
        @mcp_instance.resource(
            "am://backends",
            name="am_backends",
            description="All configured Alertmanager backends with live health, version, and default flag",
            mime_type="application/json",
        )
        async def list_backends_resource() -> str:
            backends = self.alertmanager_service.list_backends()
            result = []
            for b in backends:
                health = await self.alertmanager_service.check_health(b.id)
                version = b.version
                try:
                    status = await self.alertmanager_service.get_status(b.id)
                    version = (status.get("versionInfo") or {}).get("version")
                except Exception:
                    pass
                updated = BackendDescriptor(
                    id=b.id,
                    display_name=b.display_name,
                    base_url=b.base_url,
                    labels=b.labels,
                    health=health,
                    version=version,
                    is_default=b.is_default,
                )
                result.append(updated.model_dump())
            return json.dumps({"backends": result}, default=str, indent=2)

        @mcp_instance.resource(
            "am://backends/{backend_id}",
            name="am_backend_detail",
            description="Detailed status, readiness, version, uptime, and cluster peers for a specific Alertmanager backend",
            mime_type="application/json",
        )
        async def get_backend_detail_resource(backend_id: str) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            health = await self.alertmanager_service.check_health(bid)
            ready = await self.alertmanager_service.check_ready(bid)
            status = await self.alertmanager_service.get_status(bid)
            backends = self.alertmanager_service.list_backends()
            backend = next((b for b in backends if b.id == bid), None)
            version_info = status.get("versionInfo", {})
            return json.dumps(
                {
                    "backend": {
                        "id": bid,
                        "display_name": (
                            backend.display_name if backend else bid
                        ),
                        "base_url": backend.base_url if backend else "",
                        "labels": backend.labels if backend else {},
                        "health": health,
                        "ready": ready,
                        "is_default": (
                            backend.is_default if backend else False
                        ),
                        "version": version_info.get("version"),
                        "revision": version_info.get("revision"),
                        "build_date": version_info.get("buildDate"),
                    },
                    "cluster": status.get("cluster", {}),
                    "uptime": status.get("uptime"),
                },
                default=str,
                indent=2,
            )

        @mcp_instance.resource(
            "am://backends/{backend_id}/config",
            name="am_backend_config",
            description="Nested routing tree, inhibition rules, time intervals, and redacted configuration for a backend",
            mime_type="application/json",
        )
        async def get_backend_config_resource(backend_id: str) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            snapshot = await self.alertmanager_service.get_config_snapshot(bid)
            routing_tree = (
                await self.alertmanager_service.get_routing_tree_nested(bid)
            )
            redacted_cfg = await self.alertmanager_service.get_redacted_config(
                bid
            )
            intervals = TimeIntervalCatalog.from_config(redacted_cfg).intervals
            return json.dumps(
                {
                    "backend_id": bid,
                    "routing_tree": routing_tree.model_dump(),
                    "routes": [r.model_dump() for r in snapshot.routes],
                    "inhibitions": [
                        inh.model_dump() for inh in snapshot.inhibitions
                    ],
                    "time_intervals": intervals,
                    "config": redacted_cfg,
                },
                default=str,
                indent=2,
            )

        @mcp_instance.resource(
            "am://backends/{backend_id}/receivers",
            name="am_backend_receivers",
            description="Configured receivers (Slack, PagerDuty, email, webhook, OpsGenie) with redacted credentials for a backend",
            mime_type="application/json",
        )
        async def get_backend_receivers_resource(backend_id: str) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            receivers = await self.alertmanager_service.get_receivers(bid)
            return json.dumps(
                {
                    "backend_id": bid,
                    "receivers": [r.model_dump() for r in receivers],
                },
                default=str,
                indent=2,
            )
