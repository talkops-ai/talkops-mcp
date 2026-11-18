"""Kargo Warehouse detail and discovered artifacts resources."""

import json
from typing import Any

from kargo_mcp_server.models.warehouse import Warehouse
from kargo_mcp_server.resources.base import BaseResource
from kargo_mcp_server.utils.warehouse_spec_builder import detect_deprecated_warehouse_fields


class WarehouseResources(BaseResource):
    """Warehouse detail MCP resource."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://projects/{project}/warehouses/{warehouse}",
            name="kargo_warehouse_detail",
            description="Concise Warehouse status, subscriptions, lastFreightID, and discoveredArtifacts",
            mime_type="application/json",
        )
        async def get_warehouse_resource(project: str, warehouse: str) -> str:
            """Get curated Warehouse detail and discovered artifacts."""
            try:
                raw = await self.kargo_service.get_warehouse(project, warehouse)
                wh = Warehouse.model_validate(raw)
                raw_spec = raw.get("spec") if isinstance(raw, dict) else {}
                payload = {
                    "name": wh.metadata.name,
                    "project": project,
                    "ready": wh.is_ready(),
                    "interval": wh.spec.interval or "5m0s",
                    "freight_creation_policy": wh.spec.freight_creation_policy,
                    "subscription_types": wh.get_subscription_types(),
                    "subscriptions": wh.spec.subscriptions,
                    "deprecated_fields": detect_deprecated_warehouse_fields(raw_spec or {}),
                    "last_freight_id": wh.status.last_freight_id if wh.status else None,
                    "last_handled_refresh": (
                        wh.status.last_handled_refresh if wh.status else None
                    ),
                    "discovered_artifacts": (
                        wh.status.discovered_artifacts if wh.status else {}
                    ),
                    "conditions": wh.status.conditions if wh.status else [],
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps(
                    {"project": project, "warehouse": warehouse, "error": str(exc)},
                    indent=2,
                )
