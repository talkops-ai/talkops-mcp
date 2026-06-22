"""5-dimensional trace diff engine.

Compares two traces across:
1. Structure — which services/operations appear in each trace
2. Span count — per-service span count deltas
3. Timing — total duration, per-service duration deltas
4. Errors — error spans unique to each trace
5. Attributes — deep attribute key/value diff

Reuses span extraction helpers from trace_summarizer to handle
both OTLP and LLM format traces.
"""

from typing import Any, Dict, List, Set, Tuple

from tempo_mcp_server.utils.trace_summarizer import (
    _extract_spans,
    _get_attr_value,
    _get_duration_ms,
    _get_span_attr,
)


def _get_service_name(span: Dict[str, Any]) -> str:
    """Extract service name from a span (handles both OTLP and LLM formats)."""
    name = (
        _get_span_attr(span, "service.name")
        or span.get("_resource_attrs", {}).get("service.name")
        or span.get("serviceName")
        or "unknown"
    )
    return str(name)


def _is_error_span(span: Dict[str, Any]) -> bool:
    """Check if a span has error status."""
    status = span.get("status", {})
    if isinstance(status, dict):
        code = status.get("code", 0)
        if isinstance(code, str):
            return code in ("2", "STATUS_CODE_ERROR", "ERROR")
        return code == 2
    return False


def _collect_attributes(span: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Collect all attribute key-value pairs from a span into a {key: {values}} map."""
    attrs: Dict[str, Set[str]] = {}
    for attr in span.get("attributes", []):
        key = attr.get("key", "")
        if not key:
            continue
        val = _get_attr_value(attr.get("value", {}))
        attrs.setdefault(key, set()).add(str(val))
    return attrs


def _build_service_map(
    spans: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group spans by service name."""
    svc_map: Dict[str, List[Dict[str, Any]]] = {}
    for span in spans:
        svc = _get_service_name(span)
        svc_map.setdefault(svc, []).append(span)
    return svc_map


def _diff_structure(
    map_a: Dict[str, List], map_b: Dict[str, List]
) -> Dict[str, Any]:
    """Set-diff on service names."""
    keys_a = set(map_a.keys())
    keys_b = set(map_b.keys())
    return {
        "services_only_in_a": sorted(keys_a - keys_b),
        "services_only_in_b": sorted(keys_b - keys_a),
        "services_in_both": sorted(keys_a & keys_b),
    }


def _diff_span_counts(
    map_a: Dict[str, List], map_b: Dict[str, List]
) -> Dict[str, Any]:
    """Per-service span count delta."""
    all_services = sorted(set(map_a.keys()) | set(map_b.keys()))
    result: Dict[str, Any] = {}
    for svc in all_services:
        count_a = len(map_a.get(svc, []))
        count_b = len(map_b.get(svc, []))
        result[svc] = {
            "a": count_a,
            "b": count_b,
            "delta": count_b - count_a,
        }
    return result


def _total_duration_ms(spans: List[Dict[str, Any]]) -> float:
    """Compute total trace duration from span start/end bounds."""
    if not spans:
        return 0.0

    # Try to get earliest start and latest end
    starts = []
    ends = []
    for span in spans:
        start = span.get("startTimeUnixNano", 0)
        end = span.get("endTimeUnixNano", 0)
        if isinstance(start, str):
            start = int(start) if start else 0
        if isinstance(end, str):
            end = int(end) if end else 0
        if start:
            starts.append(start)
        if end:
            ends.append(end)

    if starts and ends:
        return (max(ends) - min(starts)) / 1_000_000

    # Fallback: sum of all span durations (may overcount parallel spans)
    return sum(_get_duration_ms(s) for s in spans)


def _diff_durations(
    spans_a: List[Dict[str, Any]],
    spans_b: List[Dict[str, Any]],
    map_a: Dict[str, List],
    map_b: Dict[str, List],
) -> Dict[str, Any]:
    """Total + per-service timing diff with delta_pct."""
    total_a = _total_duration_ms(spans_a)
    total_b = _total_duration_ms(spans_b)
    delta_ms = total_b - total_a
    delta_pct = f"{(delta_ms / total_a * 100):+.1f}%" if total_a > 0 else "N/A"

    # Per-service average duration
    per_service = []
    all_services = sorted(set(map_a.keys()) | set(map_b.keys()))
    for svc in all_services:
        svc_spans_a = map_a.get(svc, [])
        svc_spans_b = map_b.get(svc, [])
        avg_a = (
            sum(_get_duration_ms(s) for s in svc_spans_a) / len(svc_spans_a)
            if svc_spans_a
            else 0.0
        )
        avg_b = (
            sum(_get_duration_ms(s) for s in svc_spans_b) / len(svc_spans_b)
            if svc_spans_b
            else 0.0
        )
        per_service.append(
            {
                "service": svc,
                "a_avg_ms": round(avg_a, 2),
                "b_avg_ms": round(avg_b, 2),
                "delta_ms": round(avg_b - avg_a, 2),
            }
        )

    return {
        "total_ms": {
            "a": round(total_a, 2),
            "b": round(total_b, 2),
            "delta_ms": round(delta_ms, 2),
            "delta_pct": delta_pct,
        },
        "per_service": per_service,
    }


def _summarize_error_span(span: Dict[str, Any]) -> Dict[str, str]:
    """Create a brief summary of an error span."""
    service = _get_service_name(span)
    span_name = span.get("name", "unknown")
    status_msg = span.get("status", {}).get("message", "")

    # Try to extract exception type from events
    exception_type = ""
    for event in span.get("events", []):
        if event.get("name") == "exception":
            for attr in event.get("attributes", []):
                if attr.get("key") == "exception.type":
                    exception_type = str(_get_attr_value(attr.get("value", {})))
                    break

    summary: Dict[str, str] = {
        "service": service,
        "span_name": span_name,
    }
    if status_msg:
        summary["status_message"] = status_msg
    if exception_type:
        summary["exception_type"] = exception_type
    return summary


def _diff_errors(
    spans_a: List[Dict[str, Any]], spans_b: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Error spans unique to A, B, or common to both (by service+span_name)."""
    errors_a = [s for s in spans_a if _is_error_span(s)]
    errors_b = [s for s in spans_b if _is_error_span(s)]

    # Build signature sets for dedup
    def _sig(span: Dict[str, Any]) -> Tuple[str, str]:
        return (_get_service_name(span), span.get("name", "unknown"))

    sigs_a = {_sig(s) for s in errors_a}
    sigs_b = {_sig(s) for s in errors_b}

    only_a_sigs = sigs_a - sigs_b
    only_b_sigs = sigs_b - sigs_a
    common_sigs = sigs_a & sigs_b

    return {
        "a_error_count": len(errors_a),
        "b_error_count": len(errors_b),
        "errors_only_in_a": [
            _summarize_error_span(s) for s in errors_a if _sig(s) in only_a_sigs
        ],
        "errors_only_in_b": [
            _summarize_error_span(s) for s in errors_b if _sig(s) in only_b_sigs
        ],
        "common_errors": [
            {"service": sig[0], "span_name": sig[1]} for sig in sorted(common_sigs)
        ],
    }


def _diff_attributes(
    spans_a: List[Dict[str, Any]], spans_b: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Deep attribute key/value diff across all spans."""
    # Merge all attribute keys and value sets
    merged_a: Dict[str, Set[str]] = {}
    merged_b: Dict[str, Set[str]] = {}

    for span in spans_a:
        for key, vals in _collect_attributes(span).items():
            merged_a.setdefault(key, set()).update(vals)

    for span in spans_b:
        for key, vals in _collect_attributes(span).items():
            merged_b.setdefault(key, set()).update(vals)

    keys_a = set(merged_a.keys())
    keys_b = set(merged_b.keys())

    # Keys only in one side
    a_only_keys = sorted(keys_a - keys_b)
    b_only_keys = sorted(keys_b - keys_a)

    # Value differences for shared keys
    value_differences = []
    for key in sorted(keys_a & keys_b):
        vals_a = merged_a[key]
        vals_b = merged_b[key]
        if vals_a != vals_b:
            value_differences.append(
                {
                    "key": key,
                    "a_values": sorted(vals_a),
                    "b_values": sorted(vals_b),
                }
            )

    return {
        "a_only_keys": a_only_keys,
        "b_only_keys": b_only_keys,
        "value_differences": value_differences,
    }


def diff_traces(
    trace_a: Dict[str, Any],
    trace_b: Dict[str, Any],
    trace_id_a: str,
    trace_id_b: str,
) -> Dict[str, Any]:
    """Compute a full multi-dimensional diff between two traces.

    Dimensions:
    1. Structural — service/operation presence
    2. Span count — per-service span count delta
    3. Timing — total + per-service duration delta
    4. Errors — error spans unique to each trace
    5. Attributes — deep attribute key/value diff

    Args:
        trace_a: Raw trace payload (OTLP or LLM format) for the baseline trace.
        trace_b: Raw trace payload (OTLP or LLM format) for the comparison trace.
        trace_id_a: Trace ID of the baseline trace.
        trace_id_b: Trace ID of the comparison trace.

    Returns:
        Dictionary with all 5 diff dimensions plus per-trace summaries.
    """
    spans_a = _extract_spans(trace_a)
    spans_b = _extract_spans(trace_b)

    map_a = _build_service_map(spans_a)
    map_b = _build_service_map(spans_b)

    services_a = sorted(map_a.keys())
    services_b = sorted(map_b.keys())

    errors_a = sum(1 for s in spans_a if _is_error_span(s))
    errors_b = sum(1 for s in spans_b if _is_error_span(s))

    return {
        "trace_a": {
            "trace_id": trace_id_a,
            "total_spans": len(spans_a),
            "services": services_a,
            "duration_ms": round(_total_duration_ms(spans_a), 2),
            "error_count": errors_a,
        },
        "trace_b": {
            "trace_id": trace_id_b,
            "total_spans": len(spans_b),
            "services": services_b,
            "duration_ms": round(_total_duration_ms(spans_b), 2),
            "error_count": errors_b,
        },
        "structural_diff": _diff_structure(map_a, map_b),
        "span_count_diff": _diff_span_counts(map_a, map_b),
        "duration_diff": _diff_durations(spans_a, spans_b, map_a, map_b),
        "error_diff": _diff_errors(spans_a, spans_b),
        "attribute_diff": _diff_attributes(spans_a, spans_b),
    }
