"""Time parsing, validation, and normalization utilities.

Handles conversion between human-readable time expressions,
RFC3339 timestamps, and nanosecond-epoch values that Loki expects.
"""

import re
from datetime import datetime, timedelta, timezone

from loki_mcp_server.exceptions import LokiValidationError

# Regex: matches relative time expressions like 'now', 'now-1h', 'now-30m'
_RELATIVE_RE = re.compile(
    r"^now(?:\s*-\s*(\d+)\s*([smhd]))?$", re.IGNORECASE
)

# Regex: matches numeric epoch values (int or float)
_EPOCH_RE = re.compile(r"^\d+\.?\d*$")

# Duration unit map
_DURATION_UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
}


def parse_relative_time(expr: str) -> str:
    """Convert a relative time expression to an RFC3339 timestamp.

    Supports: 'now', 'now-1h', 'now-30m', 'now-5d', etc.
    Passes through RFC3339 and epoch values unchanged.

    Args:
        expr: Time expression string.

    Returns:
        RFC3339 timestamp string (UTC).

    Raises:
        LokiValidationError: If the expression is unparseable.
    """
    if not expr:
        raise LokiValidationError("Empty time expression")

    expr = expr.strip()

    # If it's already RFC3339 or epoch, pass through
    if _EPOCH_RE.match(expr) or "T" in expr:
        return expr

    match = _RELATIVE_RE.match(expr)
    if not match:
        raise LokiValidationError(
            f"Invalid time expression: '{expr}'. "
            "Use RFC3339 (e.g., '2024-01-01T00:00:00Z'), "
            "epoch (e.g., '1700000000'), or relative (e.g., 'now-1h')."
        )

    now = datetime.now(timezone.utc)

    if match.group(1) is None:
        # Just 'now'
        return now.strftime("%Y-%m-%dT%H:%M:%SZ")

    amount = int(match.group(1))
    unit = match.group(2).lower()
    kwarg = _DURATION_UNITS.get(unit)

    if kwarg is None:
        raise LokiValidationError(
            f"Unknown time unit '{unit}'. Use s, m, h, or d."
        )

    past = now - timedelta(**{kwarg: amount})
    return past.strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_time_window(
    start: str, end: str, max_hours: int
) -> None:
    """Validate that a time range doesn't exceed the maximum window.

    Args:
        start: Start timestamp (RFC3339 or epoch).
        end: End timestamp (RFC3339 or epoch).
        max_hours: Maximum allowed window in hours.

    Raises:
        LokiValidationError: If the window exceeds max_hours.
    """
    start_dt = _parse_to_datetime(start)
    end_dt = _parse_to_datetime(end)

    if start_dt >= end_dt:
        raise LokiValidationError(
            f"Start time ({start}) must be before end time ({end})"
        )

    window = end_dt - start_dt
    window_hours = window.total_seconds() / 3600

    if window_hours > max_hours:
        raise LokiValidationError(
            f"Query time window of {window_hours:.1f}h exceeds maximum "
            f"of {max_hours}h ({max_hours // 24}d). "
            f"Narrow the time range."
        )


def ensure_rfc3339(time_str: str) -> str:
    """Normalize any supported time format to RFC3339.

    Args:
        time_str: RFC3339, epoch, or relative time string.

    Returns:
        RFC3339 timestamp string (UTC).
    """
    # Resolve relative expressions first
    resolved = parse_relative_time(time_str)

    # If it's already RFC3339, return it
    if "T" in resolved:
        return resolved

    # If it's an epoch, convert
    if _EPOCH_RE.match(resolved):
        ts = float(resolved)
        # If nanosecond epoch (> 1e15), convert to seconds
        if ts > 1e15:
            ts = ts / 1e9
        elif ts > 1e12:
            ts = ts / 1e3
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return resolved


def _parse_to_datetime(time_str: str) -> datetime:
    """Parse a time string to a datetime for comparison.

    Args:
        time_str: RFC3339 or epoch time string.

    Returns:
        UTC datetime object.
    """
    # Resolve relative expressions
    resolved = ensure_rfc3339(time_str)

    if "T" in resolved:
        # Handle various RFC3339 formats
        resolved = resolved.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(resolved)
        except ValueError:
            raise LokiValidationError(
                f"Cannot parse time '{time_str}' as RFC3339"
            )

    # Shouldn't reach here after ensure_rfc3339
    raise LokiValidationError(
        f"Cannot parse time '{time_str}'"
    )
