"""Kargo Stage status and sanitized YAML manifest resources."""

import json
import yaml
from typing import Any

from kargo_mcp_server.models.stage import Stage
from kargo_mcp_server.resources.base import BaseResource
from kargo_mcp_server.utils.redaction import sanitize_manifest


class StageResources(BaseResource):
    """Stage detail and sanitized YAML manifest MCP resources."""

    def register(self, mcp_instance: Any) -> None:

        @mcp_instance.resource(
            "kargo://projects/{project}/stages/{stage}",
            name="kargo_stage_detail",
            description="Concise Stage status (phase, health, currentFreight, verification, promotions, holds, conditions)",
            mime_type="application/json",
        )
        async def get_stage_detail_resource(project: str, stage: str) -> str:
            """Return concise, curated Stage status JSON."""
            try:
                raw = await self.kargo_service.get_stage(project, stage)
                stg = Stage.model_validate(raw)
                payload = {
                    "name": stg.metadata.name,
                    "project": project,
                    "phase": stg.get_phase(),
                    "health_status": stg.get_health_status(),
                    "current_freight": stg.get_current_freight_id(),
                    "previous_verified_freight": stg.get_previous_verified_freight_id(),
                    "requested_freight": [
                        rf.model_dump(by_alias=True, exclude_none=True)
                        for rf in stg.spec.requested_freight
                    ],
                    "current_promotion": stg.status.current_promotion if stg.status else None,
                    "last_promotion": stg.status.last_promotion if stg.status else None,
                    "latest_verification": stg.get_latest_verification(),
                    "auto_promotion_enabled": (
                        stg.status.auto_promotion_enabled if stg.status else None
                    ),
                    "auto_promotion_holds": (
                        (stg.status.effective_auto_promotion_holds or stg.status.auto_promotion_holds)
                        if stg.status
                        else []
                    ),
                    "conditions": stg.status.conditions if stg.status else [],
                }
                return json.dumps(payload, indent=2, default=str)
            except Exception as exc:
                return json.dumps(
                    {"project": project, "stage": stage, "error": str(exc)},
                    indent=2,
                )

        @mcp_instance.resource(
            "kargo://projects/{project}/stages/{stage}/manifest",
            name="kargo_stage_manifest",
            description="Sanitized YAML manifest for a Kargo Stage (strips managedFields and redacts literal env secrets)",
            mime_type="application/x-yaml",
        )
        async def get_stage_manifest_resource(project: str, stage: str) -> str:
            """Return sanitized YAML manifest for a Stage."""
            try:
                raw = await self.kargo_service.get_stage(project, stage)
                sanitized = sanitize_manifest(raw)
                return yaml.dump(sanitized, default_flow_style=False)
            except Exception as exc:
                return json.dumps(
                    {"project": project, "stage": stage, "error": str(exc)},
                    indent=2,
                )
