"""Audit log MCP resource (`prom://audit/recent`)."""

import json
from prometheus_mcp_server.exceptions import PrometheusResourceError
from prometheus_mcp_server.resources.base import BaseResource
from prometheus_mcp_server.utils.audit import get_audit_entries


class AuditResources(BaseResource):
    """Audit log MCP resources."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "prom://audit/recent",
            name="prom_audit_recent",
            description="Recent MCP write and dry-run operations with outcomes and timestamps",
            mime_type="application/json",
        )
        async def recent_audit_resource() -> str:
            try:
                cfg = self.service_locator.get("config") if hasattr(self, "service_locator") else None
                log_path = getattr(cfg, "audit_log_path", None) if cfg else None
                entries = get_audit_entries(limit=100, audit_log_path=log_path)
                return json.dumps(
                    {
                        "entries": entries,
                        "count": len(entries),
                    },
                    default=str,
                    indent=2,
                )
            except Exception as e:
                raise PrometheusResourceError(f"Failed to read audit log: {e}")
