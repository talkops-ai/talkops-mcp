"""In-memory and optional JSONL-persisted audit log for MCP operations."""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from alertmanager_mcp_server.models.audit import AuditLogEntry, AuditOutcome

logger = logging.getLogger(__name__)

# Thread-safe bounded deque for audit entries (max 500 entries).
_AUDIT_LOG: deque[AuditLogEntry] = deque(maxlen=500)


def add_audit_entry(
    backend_id: str,
    operation: str,
    principal: str,
    summary: str,
    *,
    outcome: AuditOutcome = "succeeded",
    details: Optional[Dict[str, Any]] = None,
    audit_log_path: Optional[str] = None,
) -> AuditLogEntry:
    """Record an MCP operation for governance, compliance, and debugging."""
    entry = AuditLogEntry(
        timestamp=datetime.now(timezone.utc),
        backend_id=backend_id,
        operation=operation,
        principal=principal,
        summary=summary,
        outcome=outcome,
        details=dict(details or {}),
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

    sink_path = audit_log_path or os.getenv("AM_AUDIT_LOG_PATH")
    if sink_path:
        try:
            target = Path(sink_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(entry.model_dump_json() + "\n")
        except OSError as exc:
            logger.warning("Failed to append audit log entry to %s: %s", sink_path, exc)

    return entry


def _load_jsonl_entries(file_path: Optional[str]) -> List[AuditLogEntry]:
    """Load persisted `AuditLogEntry` records from a JSONL file if present."""
    if not file_path or not file_path.strip():
        return []
    target = Path(file_path.strip())
    if not target.is_file():
        return []
    loaded: List[AuditLogEntry] = []
    try:
        for raw_line in target.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                loaded.append(AuditLogEntry.model_validate_json(line))
            except Exception as exc:
                logger.debug("Skipping malformed audit JSONL line in %s: %s", target, exc)
    except OSError as exc:
        logger.debug("Failed to read audit log %s: %s", target, exc)
    return loaded


def get_audit_entries(audit_log_path: Optional[str] = None) -> List[AuditLogEntry]:
    """Return audit entries merged across optional seed/sink JSONL files and in-memory log."""
    seed_entries = _load_jsonl_entries(os.getenv("AM_SEED_AUDIT_LOG_PATH"))
    sink_entries = _load_jsonl_entries(audit_log_path or os.getenv("AM_AUDIT_LOG_PATH"))
    mem_entries = list(_AUDIT_LOG)

    if not seed_entries and not sink_entries:
        return mem_entries

    merged: List[AuditLogEntry] = []
    seen_keys: set[tuple[str, str, str, str, str, str]] = set()
    for entry in (*seed_entries, *sink_entries, *mem_entries):
        key = (
            entry.timestamp.isoformat(),
            entry.backend_id,
            entry.operation,
            entry.principal,
            entry.outcome,
            entry.summary,
        )
        if key not in seen_keys:
            seen_keys.add(key)
            merged.append(entry)

    merged.sort(key=lambda e: e.timestamp)
    return merged[-500:]


def clear_audit_log() -> None:
    """Clear audit log (mainly for testing)."""
    _AUDIT_LOG.clear()
