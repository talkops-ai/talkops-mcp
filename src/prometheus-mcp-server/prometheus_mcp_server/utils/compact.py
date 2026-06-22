"""Compact serialization for Prometheus query results.

Reduces payload size for LLM consumption by:
1. Extracting common labels shared across all samples
2. Truncating floating-point value precision
3. Stripping the redundant __name__ label
"""

from typing import Any, Dict, List, Optional, Set


def compact_instant_result(
    result_dict: Dict[str, Any],
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """Compact an instant query result dict for LLM consumption.

    Expects format: {"resultType": "...", "result": [...], ...}

    Args:
        result_dict: The raw instant query result dict.
        query: The original PromQL query (used for context).

    Returns:
        Compacted dict with common_labels extracted and values trimmed.
    """
    samples = result_dict.get("result")
    if not samples or not isinstance(samples, list):
        return result_dict

    # Extract and compact
    common_labels = _extract_common_labels(
        [s.get("metric", {}) for s in samples if isinstance(s, dict)]
    )
    compacted_samples = []
    for sample in samples:
        if not isinstance(sample, dict):
            compacted_samples.append(sample)
            continue

        metric = dict(sample.get("metric", {}))
        # Remove common labels and __name__ from individual metrics
        for key in common_labels:
            metric.pop(key, None)
        metric.pop("__name__", None)

        # Compact the value precision
        value = sample.get("value")
        if value and isinstance(value, (list, tuple)) and len(value) == 2:
            value = [value[0], _compact_value(value[1])]

        compacted_samples.append({"metric": metric, "value": value})

    compacted = dict(result_dict)
    compacted["result"] = compacted_samples

    # Add common labels at the top level if any were extracted
    if common_labels:
        compacted["common_labels"] = common_labels

    return compacted


def compact_range_result(
    result_dict: Dict[str, Any],
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """Compact a range query result dict for LLM consumption.

    Expects format: {"series": [...], "downsampling": {...}, ...}

    Args:
        result_dict: The raw range query result dict.
        query: The original PromQL query (used for context).

    Returns:
        Compacted dict with common_labels extracted and values trimmed.
    """
    series_list = result_dict.get("series")
    if not series_list or not isinstance(series_list, list):
        return result_dict

    common_labels = _extract_common_labels(
        [s.get("metric", {}) for s in series_list if isinstance(s, dict)]
    )
    compacted_series = []
    for series in series_list:
        if not isinstance(series, dict):
            compacted_series.append(series)
            continue

        metric = dict(series.get("metric", {}))
        for key in common_labels:
            metric.pop(key, None)
        metric.pop("__name__", None)

        # Compact each value in the values array
        values = series.get("values", [])
        compacted_values = []
        for v in values:
            if isinstance(v, (list, tuple)) and len(v) == 2:
                compacted_values.append([v[0], _compact_value(v[1])])
            else:
                compacted_values.append(v)

        compacted_series.append({"metric": metric, "values": compacted_values})

    compacted = dict(result_dict)
    compacted["series"] = compacted_series

    if common_labels:
        compacted["common_labels"] = common_labels

    return compacted


def _extract_common_labels(metrics: List[Dict[str, str]]) -> Dict[str, str]:
    """Extract labels that have the same value across ALL samples.

    These are redundant per-sample and can be factored out to
    a top-level common_labels dict.
    """
    if not metrics:
        return {}

    # Start with all labels from the first metric
    first = metrics[0]
    if not first:
        return {}

    # Candidate common labels: present in first metric, excluding __name__
    candidates: Dict[str, str] = {
        k: v for k, v in first.items() if k != "__name__"
    }

    # Check against all other metrics
    for metric in metrics[1:]:
        if not metric:
            return {}  # If any sample has no labels, no commonality
        # Remove candidates that don't match
        to_remove: List[str] = []
        for key, value in candidates.items():
            if metric.get(key) != value:
                to_remove.append(key)
        for key in to_remove:
            del candidates[key]

        if not candidates:
            return {}

    return candidates


def _compact_value(val: Any) -> str:
    """Compact a Prometheus value string to 6 significant digits.

    Prometheus stores float64 but for LLM consumption, 6 significant
    digits is sufficient precision.
    """
    if not isinstance(val, str):
        return str(val)
    try:
        f = float(val)
        # Preserve integer values exactly
        if f == int(f) and abs(f) < 1e15:
            return str(int(f))
        # Use 6 significant digits
        return f"{f:.6g}"
    except (ValueError, OverflowError):
        return val
