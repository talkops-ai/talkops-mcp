"""Kargo Freight detail resource."""

import json
from typing import Any

from kargo_mcp_server.models.freight import Freight
from kargo_mcp_server.resources.base import BaseResource


class FreightResources(BaseResource):
    """Freight detail MCP resource."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://projects/{project}/freight/{freight_or_alias}",
            name="kargo_freight_detail",
            description="Detailed Freight bundle (SHA-1 id, alias, origin Warehouse, commits, images, charts, stage states)",
            mime_type="application/json",
        )
        async def get_freight_resource(project: str, freight_or_alias: str) -> str:
            """Get curated Freight detail by SHA-1 id or alias."""
            try:
                raw = await self.kargo_service.get_freight(project, freight_or_alias)
                freight = Freight.model_validate(raw)
                summary = freight.to_summary()
                payload = {
                    "id": freight.metadata.name,
                    "project": project,
                    "alias": summary.alias,
                    "origin": summary.origin,
                    "discovered_at": summary.discovered_at,
                    "commits": [c.model_dump(by_alias=True, exclude_none=True) for c in freight.commits],
                    "images": [i.model_dump(by_alias=True, exclude_none=True) for i in freight.images],
                    "charts": [ch.model_dump(by_alias=True, exclude_none=True) for ch in freight.charts],
                    "currently_in": summary.currently_in,
                    "verified_in": summary.verified_in,
                    "approved_for": summary.approved_for,
                    "per_stage": [s.model_dump(exclude_none=True) for s in summary.per_stage],
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps(
                    {"project": project, "freight": freight_or_alias, "error": str(exc)},
                    indent=2,
                )
