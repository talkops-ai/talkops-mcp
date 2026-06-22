"""LogQL query validation and helper utilities.

Enforces Loki best practices:
- High-cardinality labels must NOT appear in {} stream selectors
- Pattern parser is preferred over regexp
- Stream selectors must be well-formed
"""

import logging
import re
from typing import Dict, List, Optional

from loki_mcp_server.exceptions import LokiValidationError

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# High-Cardinality Label Registry
# ──────────────────────────────────────────────

# Labels that should NEVER be placed inside {} stream selectors.
# They cause cardinality explosions and should be used as
# structured metadata filters or line filters instead.
HIGH_CARDINALITY_LABELS: set[str] = {
    "trace_id",
    "traceID",
    "traceId",
    "span_id",
    "spanID",
    "spanId",
    "user_id",
    "userId",
    "order_id",
    "orderId",
    "request_id",
    "requestID",
    "requestId",
    "ip",
    "ip_address",
    "session_id",
    "sessionID",
    "sessionId",
    "correlation_id",
    "correlationID",
    "correlationId",
    "transaction_id",
    "transactionID",
    "msg",
    "message",
}

# Regex to extract the content inside the first {} selector
_SELECTOR_CONTENT_RE = re.compile(r"\{([^}]*)\}")

# Regex to extract label names from selector content
_LABEL_NAME_RE = re.compile(r"\b(\w+)\s*[=!~]")

# Regex to detect a bare label matcher without enclosing braces.
# Matches patterns like:  label="value"  or  label!="value"  or  label=~"regex"
# but NOT patterns that already start with { or contain pipe stages.
_BARE_MATCHER_RE = re.compile(
    r"^(\w+\s*[=!~]{1,2}\s*\"[^\"]*\""  # first matcher
    r"(?:\s*,\s*\w+\s*[=!~]{1,2}\s*\"[^\"]*\")*"  # optional comma-separated matchers
    r")(.*)$",  # optional trailing pipeline
    re.DOTALL,
)


def _try_auto_wrap_braces(query: str) -> Optional[str]:
    """Attempt to auto-wrap a bare label matcher in curly braces.

    Handles the common LLM mistake of sending:
        service_name="frontend-proxy-service"
    instead of:
        {service_name="frontend-proxy-service"}

    Returns the corrected query, or None if auto-fix is not possible.
    """
    stripped = query.strip()

    # Remove accidental surrounding single quotes that LLMs sometimes add
    if stripped.startswith("'") and stripped.endswith("'"):
        stripped = stripped[1:-1].strip()

    # Already has braces — nothing to fix
    if "{" in stripped:
        return None

    m = _BARE_MATCHER_RE.match(stripped)
    if m:
        selector_part = m.group(1).strip()
        pipeline_part = m.group(2).strip()
        fixed = "{" + selector_part + "}"
        if pipeline_part:
            fixed += " " + pipeline_part
        return fixed

    return None


def validate_stream_selector(query: str) -> str:
    """Validate that a LogQL query has a proper stream selector.

    If the query is a bare label matcher without curly braces
    (a common LLM mistake), it is automatically wrapped.

    Args:
        query: LogQL query string.

    Returns:
        The (possibly auto-corrected) query string.

    Raises:
        LokiValidationError: If the query doesn't contain
            a valid {label=value} stream selector and cannot
            be auto-fixed.
    """
    if not query:
        raise LokiValidationError("LogQL query must not be empty")

    stripped = query.strip()

    # ── Auto-fix bare matchers ───────────────────────────────
    if "{" not in stripped:
        fixed = _try_auto_wrap_braces(stripped)
        if fixed:
            logger.info(
                "Auto-wrapped bare matcher: '%s' → '%s'",
                stripped[:80], fixed[:80],
            )
            return fixed

        # Cannot auto-fix — give an actionable error
        raise LokiValidationError(
            f"LogQL query MUST be wrapped in curly braces. "
            f"You sent: '{stripped[:60]}'. "
            f"Correct format: {{label=\"value\"}}. "
            f"Example: {{service_name=\"frontend-proxy-service\"}} "
            f"NOT service_name=\"frontend-proxy-service\""
        )

    # ── Check for balanced braces ────────────────────────────
    brace_depth = 0
    for ch in stripped:
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0:
                return stripped  # Found closing brace — valid

    raise LokiValidationError(
        "LogQL stream selector has unbalanced braces: "
        f"'{stripped[:80]}...'. "
        f"Ensure every '{{' has a matching '}}'."
    )


def detect_high_cardinality_in_selector(query: str) -> List[str]:
    """Detect high-cardinality labels placed inside {} stream selectors.

    Labels like trace_id, user_id, ip should NEVER be in the
    stream selector because they cause index cardinality explosions.
    Use structured metadata or line filters instead.

    Args:
        query: LogQL query string.

    Returns:
        List of high-cardinality label names found in the selector.
    """
    # Extract content inside the first {} block
    selector_match = _SELECTOR_CONTENT_RE.search(query)
    if not selector_match:
        return []

    selector_content = selector_match.group(1)
    label_names = _LABEL_NAME_RE.findall(selector_content)
    return [m for m in label_names if m in HIGH_CARDINALITY_LABELS]


# Hard byte ceiling for the total formatted log payload (80 KB).
# Must stay below the ResponseLimitingMiddleware threshold (100 KB)
# so we never return byte-truncated JSON that breaks the output schema.
_MAX_PAYLOAD_BYTES: int = 80_000

# Maximum characters kept per individual log line body.
_MAX_LINE_CHARS: int = 2_000


def format_log_entries(
    streams: List[Dict],
    max_lines: int,
    max_payload_bytes: int = _MAX_PAYLOAD_BYTES,
    max_line_chars: int = _MAX_LINE_CHARS,
) -> List[Dict]:
    """Format and truncate log entries for MCP response.

    Enforces two independent ceilings to guarantee the returned
    payload is always valid, structured JSON that stays under the
    MCP response-size limit:

    1. *Line count* — at most ``max_lines`` entries in total.
    2. *Byte budget* — accumulated UTF-8 size of all entry bodies
       must not exceed ``max_payload_bytes``.  Individual log lines
       longer than ``max_line_chars`` are hard-truncated with a
       ``…`` suffix before being counted against the budget.

    Args:
        streams: Raw stream data from Loki API.
        max_lines: Maximum total log lines to include.
        max_payload_bytes: Byte ceiling for the combined log body.
            Defaults to 80 KB (keeps the full JSON envelope well
            inside the 100 KB MCP limit).
        max_line_chars: Maximum characters to keep from each log
            line before truncating.  Defaults to 2 000.

    Returns:
        List of stream dicts with truncated entries.
    """
    import json as _json

    total_lines = 0
    payload_bytes = 0
    result: List[Dict] = []

    for stream in streams:
        labels = stream.get("stream", {})
        values = stream.get("values", [])
        entries = []

        for entry in values:
            if total_lines >= max_lines:
                break

            ts = entry[0] if len(entry) > 0 else ""
            line_body = entry[1] if len(entry) > 1 else ""

            # Hard-truncate individual log lines that are too verbose.
            if len(line_body) > max_line_chars:
                line_body = line_body[:max_line_chars] + "…[truncated]"

            # Estimate byte cost of this entry as serialised JSON.
            entry_bytes = len(
                _json.dumps({"timestamp": ts, "line": line_body},
                            ensure_ascii=False)
            )
            if payload_bytes + entry_bytes > max_payload_bytes:
                # Budget exhausted — stop adding entries.
                break

            entries.append({"timestamp": ts, "line": line_body})
            total_lines += 1
            payload_bytes += entry_bytes

        result.append({"labels": labels, "entries": entries})

        if total_lines >= max_lines or payload_bytes >= max_payload_bytes:
            break

    return result


def suggest_pattern_from_lines(lines: List[str]) -> Optional[str]:
    """Heuristic: infer a | pattern expression from sample log lines.

    Looks for common patterns like IP addresses, timestamps,
    HTTP methods, status codes, and replaces them with named
    fields for Loki's pattern parser.

    Args:
        lines: Sample log lines (at least 3 recommended).

    Returns:
        Suggested `| pattern "<pattern>"` expression, or None if
        no pattern could be inferred.
    """
    if not lines or len(lines) < 2:
        return None

    # Heuristic: look for common log patterns
    # Apache/Nginx combined log format
    _COMBINED_LOG_RE = re.compile(
        r'^\S+ \S+ \S+ \[.+\] "[A-Z]+ .+" \d+ \d+'
    )

    # Check if most lines match combined log format
    match_count = sum(
        1 for line in lines[:10] if _COMBINED_LOG_RE.match(line)
    )
    if match_count > len(lines[:10]) * 0.5:
        return (
            '| pattern "<ip> <_> <_> [<timestamp>] '
            '"<method> <path> <_>" <status> <bytes>"'
        )

    # JSON log detection
    json_count = sum(
        1 for line in lines[:10]
        if line.strip().startswith("{") and line.strip().endswith("}")
    )
    if json_count > len(lines[:10]) * 0.5:
        return "| json"

    # Key=value log detection
    kv_count = sum(
        1 for line in lines[:10]
        if re.search(r'\w+=\S+', line)
    )
    if kv_count > len(lines[:10]) * 0.5:
        return "| logfmt"

    return None
