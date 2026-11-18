"""Backend-scoped silence snapshot and single-silence detail resources."""

from __future__ import annotations

import json
from typing import Any

from alertmanager_mcp_server.resources.base import BaseResource


class SilenceResources(BaseResource):
    def register(self, mcp_instance: Any) -> None:
        @mcp_instance.resource(
            "am://backends/{backend_id}/silences/active",
            name="am_backend_active_silences",
            description="Snapshot of active silences for a specific Alertmanager backend",
            mime_type="application/json",
        )
        async def active_silences_resource(backend_id: str) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            silences, total, has_more, _ = (
                await self.alertmanager_service.list_silences_with_total(
                    bid, state="active", limit=50, offset=0
                )
            )
            return json.dumps(
                {
                    "backend_id": bid,
                    "total": total,
                    "has_more": has_more,
                    "silences": [s.model_dump(mode="json") for s in silences],
                },
                default=str,
                indent=2,
            )

        @mcp_instance.resource(
            "am://backends/{backend_id}/silences/{silence_id}",
            name="am_backend_silence_detail",
            description="Full details and status for a specific silence ID on a backend",
            mime_type="application/json",
        )
        async def silence_detail_resource(
            backend_id: str, silence_id: str
        ) -> str:
            bid = self.alertmanager_service.resolve_backend_id(backend_id)
            silence = await self.alertmanager_service.get_silence(
                bid, silence_id
            )
            return json.dumps(
                {
                    "backend_id": bid,
                    "silence": silence.model_dump(mode="json"),
                },
                default=str,
                indent=2,
            )
