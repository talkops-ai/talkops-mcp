"""Trace ID extraction from log lines and text.

Supports standard 32-character hex trace IDs and 16-character short IDs.
"""

import re
from typing import Optional

# Match 16-32 hex character trace IDs
# Must be bounded by non-hex chars or string boundaries
_TRACE_ID_PATTERN = re.compile(
    r"(?:trace[_\-]?id[=:\s\"']+)([0-9a-fA-F]{16,32})"
    r"|(?:traceid[=:\s\"']+)([0-9a-fA-F]{16,32})"
    r"|(?:TraceID[=:\s\"']+)([0-9a-fA-F]{16,32})"
    r"|(?:traceID[=:\s\"']+)([0-9a-fA-F]{16,32})"
    r"|\b([0-9a-fA-F]{32})\b",
    re.IGNORECASE,
)


def extract_trace_id(text: str) -> Optional[str]:
    """Extract a trace ID from a log line or arbitrary text.

    Searches for patterns like:
    - trace_id=abc123def456...
    - traceId: abc123def456...
    - TraceID="abc123def456..."
    - Standalone 32-char hex string

    Returns the first match, or None if no trace ID found.
    """
    if not text:
        return None

    match = _TRACE_ID_PATTERN.search(text)
    if match:
        # Return the first non-None group
        for group in match.groups():
            if group:
                return group.lower()

    return None
