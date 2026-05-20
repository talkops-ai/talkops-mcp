"""Audit log resources."""
import json
from alertmanager_mcp_server.resources.base import BaseResource
from alertmanager_mcp_server.utils.audit import get_audit_entries


class AuditResources(BaseResource):
    def register(self, mcp_instance) -> None:
        @mcp_instance.resource("am://system/audit-log", name="am_audit_log",
                               description="Recent MCP-initiated operations (create/expire/extend silence, push test alert)",
                               mime_type="application/json")
        async def audit_log_resource() -> str:
            entries = get_audit_entries()
            return json.dumps(
                {"entries": [e.model_dump(mode="json") for e in entries]},
                default=str, indent=2,
            )
