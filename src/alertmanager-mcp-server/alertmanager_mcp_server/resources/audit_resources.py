"""Audit log resource (`am://audit-log`)."""

from __future__ import annotations

import json
from typing import Any

from alertmanager_mcp_server.resources.base import BaseResource
from alertmanager_mcp_server.utils.audit import get_audit_entries


class AuditResources(BaseResource):
    def register(self, mcp_instance: Any) -> None:
        @mcp_instance.resource(
            "am://audit-log",
            name="am_audit_log",
            description="Recent MCP-initiated operations (create/update/expire silence, push test alert, policy denials)",
            mime_type="application/json",
        )
        async def audit_log_resource() -> str:
            entries = get_audit_entries(
                audit_log_path=self.alertmanager_service.config.audit_log_path
            )
            return json.dumps(
                {
                    "total": len(entries),
                    "entries": [e.model_dump(mode="json") for e in entries],
                },
                default=str,
                indent=2,
            )
