"""Time parsing and normalization utilities.

Tempo uses epoch seconds for most APIs and nanoseconds for trace timestamps.
"""

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

_DURATION_PATTERN = re.compile(
    r"^(\d+)(s|m|h|d|w)$", re.IGNORECASE
)

_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


def duration_to_seconds(duration_str: str) -> float:
    """Convert a duration string (e.g. '3h', '30m', '7d') to seconds.

    Unlike parse_since, returns a raw float instead of a timedelta —
    useful for numeric comparisons (e.g. max-duration validation).

    Raises ValueError on invalid format.
    """
    match = _DURATION_PATTERN.match(duration_str.strip())
    if not match:
        raise ValueError(
            f"Invalid duration format: '{duration_str}'. "
            "Expected format: <number><unit> where unit is s/m/h/d/w"
        )
    value = int(match.group(1))
    unit = match.group(2).lower()
    return float(value * _UNITS[unit])


def parse_since(since_str: str) -> timedelta:
    """Parse a relative duration string to timedelta.

    Supported formats: "30s", "15m", "1h", "7d", "2w"
    """
    return timedelta(seconds=duration_to_seconds(since_str))


def to_epoch_seconds(dt: datetime) -> float:
    """Convert datetime to Unix epoch seconds."""
    return dt.timestamp()


def to_epoch_nanos(dt: datetime) -> int:
    """Convert datetime to Unix epoch nanoseconds (used by Tempo trace timestamps)."""
    return int(dt.timestamp() * 1_000_000_000)


def resolve_time_params(
    start: Optional[float] = None,
    end: Optional[float] = None,
    since: Optional[str] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Normalize time range inputs.

    Priority:
    1. If start and end are provided, use them directly
    2. If since is provided, compute start from now minus duration
    3. If only end is provided, use it as-is

    Returns:
        Tuple of (start_epoch_seconds, end_epoch_seconds)
    """
    now = time.time()

    if since:
        delta = parse_since(since)
        computed_start = now - delta.total_seconds()
        return (computed_start, end if end is not None else now)

    # M-04: use `is not None` instead of truthiness so that start=0.0 / end=0.0
    # (epoch zero, technically valid) are handled correctly and not treated as
    # "not provided".
    if start is not None and end is None:
        return (start, now)

    return (start, end)
