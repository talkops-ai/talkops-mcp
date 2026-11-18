"""In-memory bounded ring-buffer and optional JSONL audit log for MCP write operations."""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from prometheus_mcp_server.utils.redaction import redact_sensitive_data

logger = logging.getLogger(__name__)

AuditOutcome = Literal[
    "succeeded",
    "dry_run",
    "denied",
    "aborted",
    "confirmation_required",
    "failed",
]


@dataclass
class AuditLogEntry:
    """Structured audit log entry for an MCP write or administrative operation."""

    timestamp: str
    backend_id: str
    operation: str
    principal: str
    summary: str
    outcome: AuditOutcome = "succeeded"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize audit entry to a JSON-compatible dictionary."""
        return asdict(self)


_AUDIT_LOG: deque[AuditLogEntry] = deque(maxlen=500)


def add_audit_entry(
    backend_id: str,
    operation: str,
    summary: str,
    *,
    principal: str = "mcp-agent",
    outcome: AuditOutcome = "succeeded",
    details: Optional[Dict[str, Any]] = None,
    audit_log_path: Optional[str] = None,
) -> AuditLogEntry:
    """Record an MCP write or dry-run operation with automatic secret redaction."""
    safe_details = redact_sensitive_data(dict(details or {}))
    entry = AuditLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        backend_id=backend_id,
        operation=operation,
        principal=principal,
        summary=summary,
        outcome=outcome,
        details=safe_details,
    )
    _AUDIT_LOG.append(entry)
    logger.info(
        "audit: %s [%s] %s on %s by %s",
        operation,
        outcome,
        summary,
        backend_id,
        principal,
    )

    sink_path = audit_log_path or os.getenv("PROMETHEUS_AUDIT_LOG_PATH")
    if sink_path:
        try:
            target = Path(sink_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.to_dict()) + "\n")
        except OSError as exc:
            logger.warning("Failed to append audit log entry to %s: %s", sink_path, exc)

    return entry


def get_audit_entries(
    limit: int = 100, audit_log_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return recent audit entries as dictionaries (most recent first), merging persisted JSONL if configured."""
    merged: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    sink_path = audit_log_path or os.getenv("PROMETHEUS_AUDIT_LOG_PATH") or os.getenv("MCP_AUDIT_LOG_PATH")
    if sink_path:
        try:
            target = Path(sink_path)
            if target.is_file():
                for raw_line in target.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict):
                        sig = (
                            str(obj.get("timestamp", "")),
                            str(obj.get("operation", "")),
                            str(obj.get("summary", "")),
                            str(obj.get("outcome", "")),
                        )
                        if sig not in seen:
                            seen.add(sig)
                            merged.append(obj)
        except OSError:
            pass

    for entry in _AUDIT_LOG:
        d = entry.to_dict()
        sig = (
            str(d.get("timestamp", "")),
            str(d.get("operation", "")),
            str(d.get("summary", "")),
            str(d.get("outcome", "")),
        )
        if sig not in seen:
            seen.add(sig)
            merged.append(d)

    merged.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return merged[: max(1, limit)]


def clear_audit_log() -> None:
    """Clear in-memory audit log (used in test fixtures)."""
    _AUDIT_LOG.clear()
