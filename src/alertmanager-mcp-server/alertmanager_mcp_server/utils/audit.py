"""In-memory audit log for MCP-initiated operations."""

import logging
from collections import deque
from datetime import datetime, timezone
from typing import List

from alertmanager_mcp_server.models.audit import AuditLogEntry

logger = logging.getLogger(__name__)

# Thread-safe bounded deque for audit entries (max 500 entries).
_AUDIT_LOG: deque[AuditLogEntry] = deque(maxlen=500)


def add_audit_entry(
    backend_id: str,
    operation: str,
    principal: str,
    summary: str,
) -> None:
    """Record a mutating MCP operation for governance and debugging."""
    entry = AuditLogEntry(
        timestamp=datetime.now(timezone.utc),
        backend_id=backend_id,
        operation=operation,
        principal=principal,
        summary=summary,
    )
    _AUDIT_LOG.append(entry)
    logger.info("audit: %s %s on %s by %s", operation, summary, backend_id, principal)


def get_audit_entries() -> List[AuditLogEntry]:
    """Return all audit entries (most recent last)."""
    return list(_AUDIT_LOG)


def clear_audit_log() -> None:
    """Clear audit log (mainly for testing)."""
    _AUDIT_LOG.clear()
