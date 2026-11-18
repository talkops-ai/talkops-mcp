"""Trace ID and W3C traceparent extraction from log lines and text.

Supports:
- W3C traceparent headers: 00-<32hex_trace_id>-<16hex_span_id>-<2hex_flags>
- Structured JSON logs: "trace_id", "traceId", "otelTraceID", "dd.trace_id"
- Logfmt / key-value logs: trace_id=..., traceId: ..., tid=...
- Standalone 32-character hex trace IDs
Rejects invalid all-zero trace IDs (00000000000000000000000000000000).
"""

import re
from typing import Dict, Optional

# 1. W3C traceparent: version(2hex)-trace_id(32hex)-parent_id(16hex)-flags(2hex)
_W3C_TRACEPARENT_RE = re.compile(
    r"\b([0-9a-fA-F]{2})-([0-9a-fA-F]{32})-([0-9a-fA-F]{16})-([0-9a-fA-F]{2})\b"
)

# 2. Explicit key=value or JSON "key": "value" patterns (16 to 32 hex chars)
_KEYED_TRACE_ID_RE = re.compile(
    r'(?:["\']?(?:trace[_\-]?id|otelTraceID|otel\.trace_id|x-b3-traceid|tid)["\']?\s*[=:]\s*["\']?)'
    r"([0-9a-fA-F]{16,32})\b",
    re.IGNORECASE,
)

_KEYED_SPAN_ID_RE = re.compile(
    r'(?:["\']?(?:span[_\-]?id|otelSpanID|otel\.span_id|x-b3-spanid)["\']?\s*[=:]\s*["\']?)'
    r"([0-9a-fA-F]{16})\b",
    re.IGNORECASE,
)

# 3. Standalone 32-character hex token
_BARE_32HEX_RE = re.compile(r"\b([0-9a-fA-F]{32})\b")


def _is_valid_non_zero_hex(candidate: str) -> bool:
    """Return True if candidate is non-empty hex and not all zeros."""
    if not candidate:
        return False
    lower = candidate.lower()
    if all(c == "0" for c in lower):
        return False
    return True


def extract_trace_context(text: str) -> Dict[str, Optional[str]]:
    """Extract trace_id, optional span_id, and format from a log line or header."""
    if not text:
        return {"trace_id": None, "span_id": None, "format": None}

    # Priority 1: W3C traceparent
    w3c_match = _W3C_TRACEPARENT_RE.search(text)
    if w3c_match:
        version, trace_id, span_id, _flags = w3c_match.groups()
        if version.lower() != "ff" and _is_valid_non_zero_hex(trace_id):
            valid_span = span_id.lower() if _is_valid_non_zero_hex(span_id) else None
            return {
                "trace_id": trace_id.lower(),
                "span_id": valid_span,
                "format": "w3c_traceparent",
            }

    # Priority 2: Keyed trace_id (JSON or logfmt)
    for match in _KEYED_TRACE_ID_RE.finditer(text):
        candidate = match.group(1)
        if _is_valid_non_zero_hex(candidate):
            span_match = _KEYED_SPAN_ID_RE.search(text)
            span_id = (
                span_match.group(1).lower()
                if span_match and _is_valid_non_zero_hex(span_match.group(1))
                else None
            )
            fmt = "json" if ('"' in match.group(0) or "'" in match.group(0)) else "key_value"
            return {
                "trace_id": candidate.lower(),
                "span_id": span_id,
                "format": fmt,
            }

    # Priority 3: Bare 32-hex string
    for match in _BARE_32HEX_RE.finditer(text):
        candidate = match.group(1)
        if _is_valid_non_zero_hex(candidate):
            return {
                "trace_id": candidate.lower(),
                "span_id": None,
                "format": "bare_hex32",
            }

    return {"trace_id": None, "span_id": None, "format": None}


def extract_trace_id(text: str) -> Optional[str]:
    """Extract a trace ID from a log line, W3C traceparent header, or arbitrary text."""
    return extract_trace_context(text).get("trace_id")
