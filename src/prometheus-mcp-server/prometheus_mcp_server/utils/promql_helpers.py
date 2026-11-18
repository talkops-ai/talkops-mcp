"""PromQL helper utilities for semantic enforcement, downsampling, and series statistics."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

SAFE_COUNTER_WRAPPERS = frozenset(
    {"rate", "increase", "irate", "resets", "changes", "deriv", "idelta"}
)

_DURATION_PART_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h|d|w|y)")
_UNIT_SECONDS = {
    "ms": 0.001,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
    "y": 31536000.0,
}


def parse_duration_seconds(duration: str, default: float = 300.0) -> float:
    """Parse a Prometheus duration string (e.g. '5m', '1h30m', '2d') into seconds."""
    if not duration or not duration.strip():
        return default
    raw = duration.strip()
    try:
        return float(raw)
    except ValueError:
        pass
    matches = _DURATION_PART_RE.findall(raw)
    if not matches:
        return default
    total = 0.0
    for amount, unit in matches:
        total += float(amount) * _UNIT_SECONDS.get(unit, 1.0)
    return total if total > 0 else default


def _strip_label_selector_strings(query: str) -> str:
    """Blank out quoted label values inside `{...}` except PromQL 3.0 UTF-8 metric names."""
    # Replace key="value" or key=~"value" with key="" so metric names inside label values aren't flagged
    return re.sub(r'([a-zA-Z_][a-zA-Z0-9_]*\s*(?:=|!=|=~|!~)\s*)(?:"[^"]*"|\'[^\']*\')', r'\1""', query)


def _is_occurrence_wrapped(query: str, match_start: int) -> bool:
    """Return True if the metric token at `match_start` is enclosed inside a safe rate/increase wrapper."""
    prefix = query[:match_start]
    # Walk backwards through open parentheses to find enclosing function names
    depth = 0
    i = len(prefix) - 1
    while i >= 0:
        ch = prefix[i]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth > 0:
                depth -= 1
            else:
                # Extract function identifier immediately preceding this '('
                fn_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*$", prefix[:i])
                if fn_match and fn_match.group(1).lower() in SAFE_COUNTER_WRAPPERS:
                    return True
        i -= 1
    return False


_UNBOUNDED_NAME_REGEX_RE = re.compile(
    r'__name__\s*=~\s*(?:"\^?(?:\.\*|\.\+|\.\.\*|\.\+\.\*|\[\^"\]\*|\[\^"\]\+)\$?"|\'\^?(?:\.\*|\.\+|\.\.\*|\.\+\.\*)\$?\')'
)


def find_unbounded_metric_selector_error(query: str) -> Optional[str]:
    """Return an error string if `query` uses an unbounded match-all `__name__` regex."""
    if not query:
        return None
    if _UNBOUNDED_NAME_REGEX_RE.search(query):
        return (
            "Unbounded metric selector '{__name__=~\".+\"}' is prohibited to prevent TSDB OOM. "
            "Use prom_explore_metrics or prom://metadata/catalog to select specific metric names."
        )
    return None


def enforce_counter_rule_sync(
    metadata: Dict[str, list],
    query: str,
    allow_raw: bool = False,
) -> Optional[str]:
    """Check if a PromQL query violates the counter rate/increase rule.

    Uses token-boundary matching (preventing false positives when one metric name is
    a substring of another) and supports PromQL 3.0 UTF-8 quoted metric names and
    nested expressions.
    """
    if allow_raw or not query or not query.strip():
        return None

    sanitized = _strip_label_selector_strings(query.strip())

    # Check for unbounded metric regex anti-pattern
    unbounded_err = find_unbounded_metric_selector_error(query)
    if unbounded_err:
        return unbounded_err

    for metric_name, meta_entries in metadata.items():
        if not isinstance(meta_entries, list) or not meta_entries:
            continue
        if meta_entries[0].get("type") != "counter":
            continue
        if not metric_name or metric_name not in sanitized:
            continue

        # Match exact identifier token (not part of a larger metric name with a-zA-Z0-9_:)
        pattern = re.compile(
            rf'(?<![a-zA-Z0-9_:])(?:{re.escape(metric_name)}|"{re.escape(metric_name)}")(?![a-zA-Z0-9_:])'
        )
        matches = list(pattern.finditer(sanitized))
        if not matches:
            continue

        for m in matches:
            if not _is_occurrence_wrapped(sanitized, m.start()):
                return (
                    f"Counter metric '{metric_name}' must be wrapped in rate(), irate(), or increase(). "
                    f"Example: sum(rate({metric_name}[5m])). "
                    f"To inspect raw monotonic counter values intentionally, wrap in changes() or resets()."
                )

    return None


def downsample_series(
    values: List[Tuple[float, float]],
    max_points: int,
) -> List[Tuple[float, float]]:
    """Downsample a time series to <= max_points using average-bucket strategy."""
    if len(values) <= max_points or max_points <= 0:
        return values

    bucket_size = math.ceil(len(values) / max_points)
    downsampled: List[Tuple[float, float]] = []
    for i in range(0, len(values), bucket_size):
        bucket = values[i : i + bucket_size]
        if not bucket:
            continue
        ts = bucket[-1][0]
        avg = sum(v for _, v in bucket) / len(bucket)
        downsampled.append((ts, avg))
    return downsampled


def compute_auto_step(start: float, end: float, max_points: int = 200) -> str:
    """Compute an appropriate step duration for a range query."""
    duration = end - start
    if duration <= 0:
        return "15s"

    step_seconds = max(1, math.ceil(duration / max_points))

    if step_seconds < 60:
        return f"{step_seconds}s"
    if step_seconds < 3600:
        return f"{math.ceil(step_seconds / 60)}m"
    return f"{math.ceil(step_seconds / 3600)}h"


def compute_series_stats(values: List[Tuple[float, float]]) -> Dict[str, Any]:
    """Compute condensed statistical summary for a range query series."""
    finite_vals = [v for _, v in values if math.isfinite(v)]
    if not finite_vals:
        return {
            "sample_count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "p95": None,
            "latest": None,
            "delta_pct": None,
        }

    sorted_vals = sorted(finite_vals)
    n = len(sorted_vals)
    p95_idx = min(n - 1, max(0, math.ceil(0.95 * n) - 1))
    first_val = finite_vals[0]
    latest_val = finite_vals[-1]
    delta_pct: Optional[float] = None
    if first_val != 0:
        delta_pct = round(((latest_val - first_val) / abs(first_val)) * 100.0, 2)

    return {
        "sample_count": n,
        "min": round(sorted_vals[0], 6),
        "max": round(sorted_vals[-1], 6),
        "avg": round(sum(finite_vals) / n, 6),
        "p95": round(sorted_vals[p95_idx], 6),
        "latest": round(latest_val, 6),
        "delta_pct": delta_pct,
    }
