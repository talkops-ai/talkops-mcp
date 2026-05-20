"""PromQL helper utilities for semantic enforcement and downsampling."""

import math
from typing import Dict, List, Optional, Tuple


def enforce_counter_rule_sync(
    metadata: Dict[str, list],
    query: str,
    allow_raw: bool,
) -> Optional[str]:
    """Check if a query violates the counter rule.

    Returns an error message if violated, None otherwise.
    Uses metadata-aware checking to detect counter metrics even inside
    aggregation functions like sum(), avg(), topk().
    """
    if allow_raw:
        return None

    q = query.strip()
    safe_wrappers = {"rate", "increase", "irate", "resets", "changes"}

    # Check if the query is wrapped in a safe function at the top level
    for wrapper in safe_wrappers:
        if q.startswith(f"{wrapper}("):
            return None

    # Find all counter metric names that appear in the query
    for metric_name, meta_entries in metadata.items():
        if not isinstance(meta_entries, list) or not meta_entries:
            continue
        if meta_entries[0].get("type") != "counter":
            continue
        if metric_name not in q:
            continue
        # Check if it's wrapped in a safe function anywhere in the query
        is_safe = False
        for wrapper in safe_wrappers:
            if f"{wrapper}({metric_name}" in q or f"{wrapper}( {metric_name}" in q:
                is_safe = True
                break
        if not is_safe:
            return (
                f"Counter metric '{metric_name}' must be wrapped in rate()/increase(). "
                f"Example: rate({metric_name}[5m]). "
                f"Set allow_raw_counters=true to override."
            )
    return None


def downsample_series(
    values: List[Tuple[float, float]],
    max_points: int,
) -> List[Tuple[float, float]]:
    """Downsample a time series to <= max_points using average-bucket strategy.

    Args:
        values: List of (timestamp, value) sorted by timestamp
        max_points: Maximum number of points to return

    Returns:
        Downsampled list of (timestamp, value) tuples
    """
    if len(values) <= max_points or max_points <= 0:
        return values

    bucket_size = math.ceil(len(values) / max_points)
    downsampled: List[Tuple[float, float]] = []
    for i in range(0, len(values), bucket_size):
        bucket = values[i: i + bucket_size]
        if not bucket:
            continue
        ts = bucket[-1][0]
        avg = sum(v for _, v in bucket) / len(bucket)
        downsampled.append((ts, avg))
    return downsampled


def compute_auto_step(start: float, end: float, max_points: int = 200) -> str:
    """Compute an appropriate step duration for a range query.

    Ensures the result contains at most max_points data points per series.

    Args:
        start: Start timestamp (Unix seconds)
        end: End timestamp (Unix seconds)
        max_points: Maximum desired points per series

    Returns:
        Step string in Prometheus duration format (e.g., '30s', '5m', '1h')
    """
    duration = end - start
    if duration <= 0:
        return "15s"

    step_seconds = max(1, math.ceil(duration / max_points))

    if step_seconds < 60:
        return f"{step_seconds}s"
    elif step_seconds < 3600:
        return f"{math.ceil(step_seconds / 60)}m"
    else:
        return f"{math.ceil(step_seconds / 3600)}h"
