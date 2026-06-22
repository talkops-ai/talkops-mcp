"""Server-side trace analysis and summarization.

Provides critical path extraction, error analysis, K8s context extraction,
and headline generation from trace data.
"""

import base64
import binascii
from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.trace import (
    CriticalPathSpan,
    TraceErrorSummary,
    TraceSummaryOutput,
)


def _normalize_id(raw_id: str) -> str:
    """Normalize a span/trace ID to lowercase hex.

    C-01: The Tempo /api/v2/traces OTLP JSON payload encodes spanId and
    traceId as base64 strings (e.g. "AAEC3g=="), while /api/search returns
    them as lowercase hex (e.g. "0001a2de").  This mismatch caused the
    summarizer to silently drop all spans because its by_id dict was keyed
    on base64 strings that never matched any parentSpanId lookup.

    Strategy:
      1. If the string is already pure hex → return it lowercased.
      2. Otherwise attempt base64 decoding → convert bytes to hex.
      3. If both fail → return the string as-is (best-effort).
    """
    if not raw_id:
        return raw_id
    # Already hex?
    try:
        int(raw_id, 16)
        return raw_id.lower()
    except ValueError:
        pass
    # Try base64 decode
    try:
        # Pad if necessary
        padded = raw_id + "==" if len(raw_id) % 4 else raw_id
        decoded = base64.b64decode(padded)
        return decoded.hex()
    except (binascii.Error, ValueError):
        pass
    return raw_id


def _extract_spans(trace_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract flat list of spans from trace data (handles both LLM and OTLP formats)."""
    spans: List[Dict[str, Any]] = []

    # LLM format: may have a flat list of spans
    if isinstance(trace_data, list):
        return trace_data

    # LLM format: {"spans": [...]}
    if "spans" in trace_data:
        return trace_data["spans"]

    # OTLP format: {"resourceSpans": [{"scopeSpans": [{"spans": [...]}]}]}
    for rs in trace_data.get("resourceSpans", trace_data.get("batches", [])) or []:
        resource_attrs = {}
        resource = rs.get("resource", {})
        for attr in resource.get("attributes", []):
            resource_attrs[attr.get("key", "")] = _get_attr_value(attr.get("value", {}))

        for ss in rs.get("scopeSpans", rs.get("instrumentationLibrarySpans", [])):
            for span in ss.get("spans", []):
                span["_resource_attrs"] = resource_attrs
                spans.append(span)

    return spans


def _get_attr_value(value: Any) -> Any:
    """Extract value from OTLP attribute value wrapper."""
    if isinstance(value, dict):
        for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if key in value:
                return value[key]
    return value


def _get_span_attr(span: Dict[str, Any], key: str) -> Any:
    """Get attribute from a span."""
    for attr in span.get("attributes", []):
        if attr.get("key") == key:
            return _get_attr_value(attr.get("value", {}))
    return None


def _get_duration_ms(span: Dict[str, Any]) -> float:
    """Get span duration in milliseconds."""
    # LLM format may have durationMs directly
    if "durationMs" in span:
        return float(span["durationMs"])

    start = span.get("startTimeUnixNano", 0)
    end = span.get("endTimeUnixNano", 0)
    if isinstance(start, str):
        start = int(start)
    if isinstance(end, str):
        end = int(end)
    if start and end:
        return (end - start) / 1_000_000
    return 0.0


def _get_span_start_ns(span: Dict[str, Any]) -> int:
    """Return span start time in nanoseconds (0 if unavailable)."""
    v = span.get("startTimeUnixNano", 0)
    return int(v) if v else 0


def _get_span_end_ns(span: Dict[str, Any]) -> int:
    """Return span end time in nanoseconds (0 if unavailable)."""
    v = span.get("endTimeUnixNano", 0)
    return int(v) if v else 0


def extract_critical_path(spans: List[Dict[str, Any]]) -> List[CriticalPathSpan]:
    """Find the true critical path through the trace span DAG.

    M-01: Builds the parent→children adjacency map from parentSpanId, then
    walks every root-to-leaf path (DFS) and returns the one whose sum of
    span durations is greatest — the actual critical path.

    Falls back to top-5-by-duration if span IDs are missing.

    C-01: span IDs in OTLP JSON may be base64-encoded; they are normalized
    to hex before indexing so parent→child links resolve correctly.
    """
    if not spans:
        return []

    # Index spans by their spanId — normalize to hex first (C-01)
    by_id: Dict[str, Dict[str, Any]] = {}
    for s in spans:
        raw_sid = s.get("spanId") or s.get("span_id", "")
        sid = _normalize_id(raw_sid) if raw_sid else ""
        if sid:
            # Store the normalized ID back so parent lookups match
            s = dict(s)  # shallow copy — don't mutate caller's data
            s["_normalized_span_id"] = sid
            by_id[sid] = s

    if not by_id:
        # No span IDs — fall back to duration sort
        return _critical_path_by_duration(spans)

    # Build parent → children map (normalize parent ID too — C-01)
    children: Dict[str, List[str]] = {sid: [] for sid in by_id}
    roots: List[str] = []
    for sid, span in by_id.items():
        raw_parent = span.get("parentSpanId") or span.get("parent_span_id", "")
        parent = _normalize_id(raw_parent) if raw_parent else ""
        if parent and parent in by_id:
            children[parent].append(sid)
        else:
            roots.append(sid)

    if not roots:
        # Cycle or all spans have parents outside this trace — fall back
        return _critical_path_by_duration(spans)

    # DFS: find the root-to-leaf path with the greatest cumulative duration
    best_path: List[str] = []
    best_duration = -1.0

    stack: List[tuple] = [(root_id, [root_id], _get_duration_ms(by_id[root_id])) for root_id in roots]
    while stack:
        node_id, path, path_dur = stack.pop()
        kids = children.get(node_id, [])
        if not kids:
            # Leaf node
            if path_dur > best_duration:
                best_duration = path_dur
                best_path = path
        else:
            for child_id in kids:
                child_dur = _get_duration_ms(by_id[child_id])
                stack.append((child_id, path + [child_id], path_dur + child_dur))

    result: List[CriticalPathSpan] = []
    for i, sid in enumerate(best_path[:5]):
        span = by_id[sid]
        service = (
            _get_span_attr(span, "service.name")
            or span.get("_resource_attrs", {}).get("service.name", "unknown")
        )
        status_code = span.get("status", {}).get("code", 0)
        status_str = "error" if status_code == 2 else "ok"
        reason = "critical path root" if i == 0 else "critical path"
        result.append(CriticalPathSpan(
            service=str(service),
            span_name=span.get("name", "unknown"),
            duration_ms=_get_duration_ms(span),
            status=status_str,
            reason=reason,
        ))
    return result


def _critical_path_by_duration(spans: List[Dict[str, Any]]) -> List[CriticalPathSpan]:
    """Fallback: return top-5 spans by duration (used when spanIds are absent)."""
    sorted_spans = sorted(spans, key=lambda s: _get_duration_ms(s), reverse=True)
    path: List[CriticalPathSpan] = []
    for span in sorted_spans[:5]:
        service = (
            _get_span_attr(span, "service.name")
            or span.get("_resource_attrs", {}).get("service.name", "unknown")
        )
        status_code = span.get("status", {}).get("code", 0)
        status_str = "error" if status_code == 2 else "ok"
        path.append(CriticalPathSpan(
            service=str(service),
            span_name=span.get("name", "unknown"),
            duration_ms=_get_duration_ms(span),
            status=status_str,
            reason="longest duration" if len(path) == 0 else "high duration",
        ))
    return path


def extract_error_spans(spans: List[Dict[str, Any]]) -> List[TraceErrorSummary]:
    """Find spans with error status or exception events."""
    errors: List[TraceErrorSummary] = []

    for span in spans:
        status = span.get("status", {})
        status_code = status.get("code", 0)
        is_error = status_code == 2

        if not is_error:
            # Check for exception events
            for event in span.get("events", []):
                if event.get("name") == "exception":
                    is_error = True
                    break

        if is_error:
            service = (
                _get_span_attr(span, "service.name")
                or span.get("_resource_attrs", {}).get("service.name", "unknown")
            )

            error_type = None
            message = status.get("message", "")

            # Look for exception event details
            for event in span.get("events", []):
                if event.get("name") == "exception":
                    for attr in event.get("attributes", []):
                        key = attr.get("key", "")
                        val = _get_attr_value(attr.get("value", {}))
                        if key == "exception.type":
                            error_type = str(val)
                        elif key == "exception.message":
                            message = str(val)

            errors.append(TraceErrorSummary(
                service=str(service),
                span_name=span.get("name", "unknown"),
                error_type=error_type,
                message=message or None,
                span_id=span.get("spanId"),
            ))

    return errors


def extract_k8s_context(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pull K8s resource attributes from trace spans."""
    k8s_keys = [
        "k8s.namespace.name", "k8s.pod.name", "k8s.deployment.name",
        "k8s.node.name", "k8s.cluster.name", "k8s.container.name",
    ]
    context: Dict[str, Any] = {}
    services: set = set()

    for span in spans:
        resource_attrs = span.get("_resource_attrs", {})
        for key in k8s_keys:
            if key in resource_attrs and key not in context:
                context[key] = resource_attrs[key]

        service = resource_attrs.get("service.name")
        if service:
            services.add(service)

        # Also check span attributes
        for key in k8s_keys:
            val = _get_span_attr(span, key)
            if val and key not in context:
                context[key] = val

    if services:
        context["services"] = sorted(services)

    return context


def generate_headline(
    critical_path: List[CriticalPathSpan],
    errors: List[TraceErrorSummary],
    total_duration_ms: float,
    critical_path_duration_ms: float = 0.0,
    has_time_gaps: bool = False,
) -> str:
    """Generate a one-line summary of the trace."""
    parts: List[str] = []

    if total_duration_ms > 0:
        if has_time_gaps and critical_path_duration_ms > 0:
            # Disambiguate: show both wall-clock and critical path
            parts.append(
                f"{total_duration_ms:.0f}ms wall-clock "
                f"({critical_path_duration_ms:.0f}ms critical path)"
            )
        else:
            parts.append(f"{total_duration_ms:.0f}ms total")

    if errors:
        services = set(e.service for e in errors)
        parts.append(f"{len(errors)} error(s) in {', '.join(sorted(services))}")
    elif critical_path:
        parts.append(f"slowest: {critical_path[0].service}/{critical_path[0].span_name}")

    return " | ".join(parts) if parts else "Trace summary"


def summarize_trace(
    trace_id: str,
    trace_data: Dict[str, Any],
    max_spans: int = 50,
) -> TraceSummaryOutput:
    """Main entry point for server-side trace summarization."""
    spans = _extract_spans(trace_data)

    # Limit span processing
    all_spans = spans
    if len(spans) > max_spans:
        spans = sorted(spans, key=lambda s: _get_duration_ms(s), reverse=True)[:max_spans]

    critical_path = extract_critical_path(spans)
    errors = extract_error_spans(all_spans)  # Check all spans for errors
    k8s_context = extract_k8s_context(all_spans)

    total_services = len(set(
        s.get("_resource_attrs", {}).get("service.name", "unknown")
        for s in all_spans
    ))

    # H-05: Trace wall-clock duration = max(endTime) - min(startTime) across ALL
    # spans, not max(individual_span_duration). For a 3 s trace with 50 parallel
    # spans each under 100 ms, max(span_duration) would wrongly report ~100 ms.
    start_times = [_get_span_start_ns(s) for s in all_spans if _get_span_start_ns(s) > 0]
    end_times = [_get_span_end_ns(s) for s in all_spans if _get_span_end_ns(s) > 0]
    if start_times and end_times:
        total_duration = (max(end_times) - min(start_times)) / 1_000_000
    else:
        # Fall back to max individual span duration when timestamps are absent
        total_duration = max((_get_duration_ms(s) for s in all_spans), default=0.0)

    # Gap detection: compare critical path duration vs wall-clock duration.
    # When the wall-clock time is much larger than the critical execution path,
    # it means async or disjointed spans (DNS lookups, log flushes, background
    # tasks) are extending the trace window far beyond the request itself.
    critical_path_duration = sum(s.duration_ms for s in critical_path)
    has_time_gaps = False
    time_gap_note = None

    # Only flag gaps when the critical path is meaningfully shorter than
    # wall-clock time. Threshold: critical path < 50% of wall-clock AND
    # absolute gap > 100ms (avoid flagging sub-millisecond rounding noise).
    _GAP_RATIO_THRESHOLD = 0.5
    _GAP_ABS_THRESHOLD_MS = 100.0

    if (
        total_duration > 0
        and critical_path_duration > 0
        and critical_path_duration / total_duration < _GAP_RATIO_THRESHOLD
        and (total_duration - critical_path_duration) > _GAP_ABS_THRESHOLD_MS
    ):
        has_time_gaps = True
        ratio = total_duration / critical_path_duration
        time_gap_note = (
            f"Wall-clock duration ({total_duration:.0f}ms) is "
            f"{ratio:.0f}× the critical path ({critical_path_duration:.0f}ms). "
            f"This is likely due to async, background, or disjointed spans "
            f"(e.g., DNS lookups, log flushes) extending the trace window "
            f"beyond the actual request execution."
        )

    headline = generate_headline(
        critical_path, errors, total_duration,
        critical_path_duration_ms=critical_path_duration,
        has_time_gaps=has_time_gaps,
    )

    # Generate recommended next queries
    next_queries: List[str] = []
    if errors:
        svc = errors[0].service
        next_queries.append(f'{{ resource.service.name = "{svc}" && status = error }}')
    if critical_path:
        svc = critical_path[0].service
        next_queries.append(
            f'{{ resource.service.name = "{svc}" && duration > {int(total_duration * 0.8)}ms }}'
        )

    # Suspected root cause
    root_cause = None
    if errors:
        root_cause = (
            f"Error in {errors[0].service}/{errors[0].span_name}"
            + (f": {errors[0].error_type}" if errors[0].error_type else "")
        )

    return TraceSummaryOutput(
        trace_id=trace_id,
        headline=headline,
        total_spans=len(all_spans),
        total_services=total_services,
        total_duration_ms=total_duration,
        critical_path_duration_ms=critical_path_duration,
        has_time_gaps=has_time_gaps,
        time_gap_note=time_gap_note,
        critical_path=critical_path,
        errors=errors,
        k8s_context=k8s_context if k8s_context else None,
        suspected_root_cause=root_cause,
        recommended_next_queries=next_queries,
    )
