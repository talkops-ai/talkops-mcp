"""OTel Collector duration string parsing and formatting utilities.

The OpenTelemetry Collector uses duration strings in configuration
(e.g., ``"2ms"``, ``"1s"``, ``"15s"``) rather than raw numeric
millisecond values. This module converts between the two representations.

Supported units (case-insensitive):
- ``ns`` — nanoseconds
- ``us`` / ``µs`` — microseconds
- ``ms`` — milliseconds (default when unitless in ms-context)
- ``s``  — seconds
- ``m``  — minutes
- ``h``  — hours
"""

import re
from typing import List, Union

# Multipliers to convert each unit into milliseconds
_UNIT_TO_MS = {
    "ns": 1e-6,
    "us": 1e-3,
    "µs": 1e-3,
    "ms": 1.0,
    "s": 1_000.0,
    "m": 60_000.0,
    "h": 3_600_000.0,
}

_DURATION_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(ns|us|µs|ms|s|m|h)?\s*$",
    re.IGNORECASE,
)


def parse_duration_to_ms(value: Union[str, int, float]) -> float:
    """Convert an OTel duration string or number to milliseconds.

    Args:
        value: Duration string (``"2ms"``, ``"1s"``, ``"15s"``) or numeric
            value (treated as milliseconds).

    Returns:
        Duration in milliseconds as a float.

    Raises:
        ValueError: If the string cannot be parsed.

    Examples:
        >>> parse_duration_to_ms("2ms")
        2.0
        >>> parse_duration_to_ms("1s")
        1000.0
        >>> parse_duration_to_ms("1.5m")
        90000.0
        >>> parse_duration_to_ms(500)
        500.0
    """
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError(
            f"Cannot parse duration value: {value!r}. "
            f"Expected format: <number><unit> where unit is one of "
            f"{', '.join(sorted(set(_UNIT_TO_MS.keys())))}."
        )

    number = float(match.group(1))
    unit = (match.group(2) or "ms").lower()

    multiplier = _UNIT_TO_MS.get(unit)
    if multiplier is None:
        raise ValueError(f"Unknown duration unit: {unit!r}")

    return number * multiplier


def ms_to_duration_string(ms: float) -> str:
    """Convert a millisecond value to the most natural OTel duration string.

    Picks the largest unit that yields a clean integer representation.

    Args:
        ms: Duration in milliseconds.

    Returns:
        OTel-format duration string (e.g., ``"2ms"``, ``"1s"``, ``"1m"``).

    Examples:
        >>> ms_to_duration_string(2.0)
        '2ms'
        >>> ms_to_duration_string(1000.0)
        '1s'
        >>> ms_to_duration_string(60000.0)
        '1m'
        >>> ms_to_duration_string(1500.0)
        '1500ms'
    """
    if ms <= 0:
        return "0ms"

    # Try from largest unit down
    for unit, multiplier in [("h", 3_600_000.0), ("m", 60_000.0), ("s", 1_000.0)]:
        if ms >= multiplier and ms % multiplier == 0:
            val = int(ms / multiplier)
            return f"{val}{unit}"

    # Fall back to ms
    if ms == int(ms):
        return f"{int(ms)}ms"
    return f"{ms}ms"


def parse_bucket_list(
    buckets: List[Union[str, int, float]],
) -> List[float]:
    """Parse a list of bucket values (duration strings or numbers) to floats.

    Args:
        buckets: Mixed list of duration strings and numeric values.

    Returns:
        List of float millisecond values.
    """
    return [parse_duration_to_ms(b) for b in buckets]


def format_bucket_list(buckets: List[float]) -> List[str]:
    """Format a list of millisecond bucket values as OTel duration strings.

    Args:
        buckets: List of float millisecond values.

    Returns:
        List of OTel-format duration strings.
    """
    return [ms_to_duration_string(b) for b in buckets]
