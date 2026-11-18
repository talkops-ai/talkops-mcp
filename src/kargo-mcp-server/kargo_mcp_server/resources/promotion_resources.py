"""Kargo Promotion list and execution trace resources."""

import json
from typing import Any

from kargo_mcp_server.models.promotion import Promotion
from kargo_mcp_server.resources.base import BaseResource


class PromotionResources(BaseResource):
    """Promotion list and execution trace MCP resources."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://projects/{project}/promotions",
            name="kargo_project_promotions",
            description="Recent Promotions in a Kargo project with phase and timestamps",
            mime_type="application/json",
        )
        async def list_promotions_resource(project: str) -> str:
            """List recent promotions in a project."""
            try:
                promotions = await self.kargo_service.list_promotions(project)
                return json.dumps(
                    {
                        "project": project,
                        "count": len(promotions),
                        "promotions": [p.model_dump() for p in promotions[:25]],
                    },
                    indent=2,
                    default=str,
                )
            except Exception as exc:
                return json.dumps({"project": project, "error": str(exc)}, indent=2)

        @mcp_instance.resource(
            "kargo://projects/{project}/promotions/{promotion}",
            name="kargo_promotion_detail",
            description="Detailed Promotion execution trace (phase, message, per-step status, timings, outputs)",
            mime_type="application/json",
        )
        async def get_promotion_resource(project: str, promotion: str) -> str:
            """Get detailed Promotion execution trace."""
            try:
                raw = await self.kargo_service.get_promotion(project, promotion)
                promo = Promotion.model_validate(raw)
                step_meta = (
                    [
                        s.model_dump(by_alias=True, exclude_none=True)
                        for s in promo.status.step_execution_metadata
                    ]
                    if promo.status
                    else []
                )
                payload = {
                    "name": promo.metadata.name,
                    "project": project,
                    "stage": promo.spec.stage,
                    "freight": promo.spec.freight,
                    "phase": promo.get_phase(),
                    "message": promo.status.message if promo.status else None,
                    "current_step": promo.status.current_step if promo.status else None,
                    "started_at": promo.status.started_at if promo.status else None,
                    "finished_at": promo.status.finished_at if promo.status else None,
                    "steps_defined": promo.spec.steps,
                    "step_execution_metadata": step_meta,
                    "state_outputs": promo.status.state if promo.status else None,
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps(
                    {"project": project, "promotion": promotion, "error": str(exc)},
                    indent=2,
                )
