"""Server-side trace factual aggregation and summarization.

Computes critical path, self-time hotspots, error span inventory, deepest error span,
K8s resource context, and wall-clock vs critical-path time-gap facts from OTLP/LLM traces.
Contains zero interpretive root-cause guesses or query recommendations.
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
    them as lowercase hex (e.g. "0001a2de").
    """
    if not raw_id:
        return raw_id
    try:
        int(raw_id, 16)
        return raw_id.lower()
    except ValueError:
        pass
    try:
        padded = raw_id + "==" if len(raw_id) % 4 else raw_id
        decoded = base64.b64decode(padded)
        return decoded.hex()
    except (binascii.Error, ValueError):
        pass
    return raw_id


def _extract_spans(trace_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract flat list of spans from trace data (handles both LLM and OTLP formats)."""
    spans: List[Dict[str, Any]] = []

    if isinstance(trace_data, list):
        return trace_data

    if "spans" in trace_data:
        return trace_data["spans"]

    for rs in trace_data.get("resourceSpans", trace_data.get("batches", [])) or []:
        resource_attrs = {}
        resource = rs.get("resource", {})
        for attr in resource.get("attributes", []):
            resource_attrs[attr.get("key", "")] = _get_attr_value(attr.get("value", {}))

        for ss in rs.get("scopeSpans", rs.get("instrumentationLibrarySpans", [])):
            for span in ss.get("spans", []):
                span_copy = dict(span)
                span_copy["_resource_attrs"] = resource_attrs
                spans.append(span_copy)

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


def _is_error_status(span: Dict[str, Any]) -> bool:
    """Return True if an OTLP/ProtoJSON/LLM span carries error status."""
    status = span.get("status", {})
    if isinstance(status, dict):
        code = status.get("code", 0)
        if isinstance(code, str):
            return code.strip().upper() in ("2", "STATUS_CODE_ERROR", "ERROR")
        return code == 2
    if isinstance(status, str):
        return status.strip().upper() in ("2", "STATUS_CODE_ERROR", "ERROR")
    return False


def _merged_children_duration_ms(
    parent_id: str,
    by_id: Dict[str, Dict[str, Any]],
    children: Dict[str, List[str]],
) -> float:
    """Compute merged wall-clock duration of direct child spans (handling parallel overlap)."""
    cids = children.get(parent_id, [])
    if not cids:
        return 0.0
    intervals = []
    for cid in cids:
        cs = by_id[cid]
        s_ns = _get_span_start_ns(cs)
        e_ns = _get_span_end_ns(cs)
        if s_ns > 0 and e_ns >= s_ns:
            intervals.append((s_ns, e_ns))
        else:
            return sum(_get_duration_ms(by_id[c]) for c in cids)
    intervals.sort(key=lambda iv: iv[0])
    cur_s, cur_e = intervals[0]
    merged_ns = 0
    for s_ns, e_ns in intervals[1:]:
        if s_ns <= cur_e:
            cur_e = max(cur_e, e_ns)
        else:
            merged_ns += max(0, cur_e - cur_s)
            cur_s, cur_e = s_ns, e_ns
    merged_ns += max(0, cur_e - cur_s)
    return merged_ns / 1_000_000.0


def _build_span_graph(spans: List[Dict[str, Any]]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]], List[str], Dict[str, int]]:
    """Index spans by normalized ID and compute parent->children, roots, and node depths."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for s in spans:
        raw_sid = s.get("spanId") or s.get("span_id", "")
        sid = _normalize_id(raw_sid) if raw_sid else ""
        if sid:
            sc = dict(s)
            sc["_normalized_span_id"] = sid
            by_id[sid] = sc

    children: Dict[str, List[str]] = {sid: [] for sid in by_id}
    roots: List[str] = []
    for sid, span in by_id.items():
        raw_parent = span.get("parentSpanId") or span.get("parent_span_id", "")
        parent = _normalize_id(raw_parent) if raw_parent else ""
        if parent and parent in by_id and parent != sid:
            children[parent].append(sid)
        else:
            roots.append(sid)

    depths: Dict[str, int] = {}
    stack = [(r, 0) for r in roots]
    visited = set()
    while stack:
        nid, depth = stack.pop()
        if nid in visited:
            continue
        visited.add(nid)
        depths[nid] = depth
        for cid in children.get(nid, []):
            stack.append((cid, depth + 1))

    return by_id, children, roots, depths


def extract_critical_path(spans: List[Dict[str, Any]]) -> List[CriticalPathSpan]:
    """Find the critical path through the trace span DAG."""
    if not spans:
        return []

    by_id, children, roots, _ = _build_span_graph(spans)
    if not by_id or not roots:
        return _critical_path_by_duration(spans)

    best_path: List[str] = []
    best_duration = -1.0

    stack: List[tuple] = [(root_id, [root_id], _get_duration_ms(by_id[root_id])) for root_id in roots]
    visited_paths = set()
    while stack:
        node_id, path, path_dur = stack.pop()
        kids = [k for k in children.get(node_id, []) if k not in path]
        if not kids:
            if path_dur > best_duration:
                best_duration = path_dur
                best_path = path
        else:
            for child_id in kids:
                if (node_id, child_id) not in visited_paths:
                    visited_paths.add((node_id, child_id))
                child_dur = _get_duration_ms(by_id[child_id])
                stack.append((child_id, path + [child_id], path_dur + child_dur))

    result: List[CriticalPathSpan] = []
    for i, sid in enumerate(best_path[:5]):
        span = by_id[sid]
        service = (
            _get_span_attr(span, "service.name")
            or span.get("_resource_attrs", {}).get("service.name", "unknown")
        )
        status_str = "error" if _is_error_status(span) else "ok"
        dur = _get_duration_ms(span)
        child_dur = _merged_children_duration_ms(sid, by_id, children)
        self_time = max(0.0, dur - child_dur)
        reason = "critical path root" if i == 0 else "critical path"
        result.append(CriticalPathSpan(
            service=str(service),
            span_name=span.get("name", "unknown"),
            duration_ms=dur,
            self_time_ms=round(self_time, 3),
            status=status_str,
            reason=reason,
        ))
    return result


def extract_self_time_hotspots(spans: List[Dict[str, Any]], top_n: int = 5) -> List[CriticalPathSpan]:
    """Compute spans with the highest exclusive self-time (span duration minus direct child durations)."""
    if not spans:
        return []

    by_id, children, _, _ = _build_span_graph(spans)
    if not by_id:
        return _critical_path_by_duration(spans)[:top_n]

    hotspots: List[CriticalPathSpan] = []
    for sid, span in by_id.items():
        dur = _get_duration_ms(span)
        child_dur = _merged_children_duration_ms(sid, by_id, children)
        self_time = max(0.0, dur - child_dur)
        service = (
            _get_span_attr(span, "service.name")
            or span.get("_resource_attrs", {}).get("service.name", "unknown")
        )
        status_str = "error" if _is_error_status(span) else "ok"
        hotspots.append(CriticalPathSpan(
            service=str(service),
            span_name=span.get("name", "unknown"),
            duration_ms=dur,
            self_time_ms=round(self_time, 3),
            status=status_str,
            reason="leaf span" if not children.get(sid) else "exclusive self-time",
        ))

    hotspots.sort(key=lambda s: (s.self_time_ms or 0.0, s.duration_ms), reverse=True)
    return hotspots[:top_n]


def _critical_path_by_duration(spans: List[Dict[str, Any]]) -> List[CriticalPathSpan]:
    """Fallback: return top-5 spans by duration (used when spanIds are absent)."""
    sorted_spans = sorted(spans, key=lambda s: _get_duration_ms(s), reverse=True)
    path: List[CriticalPathSpan] = []
    for span in sorted_spans[:5]:
        service = (
            _get_span_attr(span, "service.name")
            or span.get("_resource_attrs", {}).get("service.name", "unknown")
        )
        status_str = "error" if _is_error_status(span) else "ok"
        dur = _get_duration_ms(span)
        path.append(CriticalPathSpan(
            service=str(service),
            span_name=span.get("name", "unknown"),
            duration_ms=dur,
            self_time_ms=dur,
            status=status_str,
            reason="longest duration" if len(path) == 0 else "high duration",
        ))
    return path


def extract_error_spans(spans: List[Dict[str, Any]]) -> List[TraceErrorSummary]:
    """Find spans with error status or exception events, annotated with call-tree depth."""
    errors: List[TraceErrorSummary] = []
    _, _, _, depths = _build_span_graph(spans)

    for span in spans:
        status = span.get("status", {}) if isinstance(span.get("status"), dict) else {}
        is_error = _is_error_status(span)

        if not is_error:
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

            for event in span.get("events", []):
                if event.get("name") == "exception":
                    for attr in event.get("attributes", []):
                        key = attr.get("key", "")
                        val = _get_attr_value(attr.get("value", {}))
                        if key == "exception.type":
                            error_type = str(val)
                        elif key == "exception.message":
                            message = str(val)

            raw_sid = span.get("spanId") or span.get("span_id")
            norm_sid = _normalize_id(raw_sid) if raw_sid else None
            errors.append(TraceErrorSummary(
                service=str(service),
                span_name=span.get("name", "unknown"),
                error_type=error_type,
                message=message or None,
                span_id=raw_sid,
                depth=depths.get(norm_sid, 0) if norm_sid else 0,
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
    """Generate a factual one-line summary of the trace."""
    parts: List[str] = []

    if total_duration_ms > 0:
        if has_time_gaps and critical_path_duration_ms > 0:
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
    """Main entry point for factual server-side trace summarization."""
    spans = _extract_spans(trace_data)

    all_spans = spans
    if len(spans) > max_spans:
        spans = sorted(spans, key=lambda s: _get_duration_ms(s), reverse=True)[:max_spans]

    critical_path = extract_critical_path(spans)
    self_time_hotspots = extract_self_time_hotspots(spans, top_n=5)
    errors = extract_error_spans(all_spans)
    k8s_context = extract_k8s_context(all_spans)

    total_services = len(set(
        s.get("_resource_attrs", {}).get("service.name", "unknown")
        for s in all_spans
    )) if all_spans else 0

    start_times = [_get_span_start_ns(s) for s in all_spans if _get_span_start_ns(s) > 0]
    end_times = [_get_span_end_ns(s) for s in all_spans if _get_span_end_ns(s) > 0]
    if start_times and end_times:
        total_duration = (max(end_times) - min(start_times)) / 1_000_000
    else:
        total_duration = max((_get_duration_ms(s) for s in all_spans), default=0.0)

    critical_path_duration = sum(s.duration_ms for s in critical_path)
    has_time_gaps = False
    time_gap_note = None

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
        gap_ms = total_duration - critical_path_duration
        time_gap_note = (
            f"Wall-clock duration ({total_duration:.0f}ms) is "
            f"{ratio:.1f}x the critical path ({critical_path_duration:.0f}ms); "
            f"unaccounted gap is {gap_ms:.0f}ms."
        )
    elif total_duration >= 1000.0 and spans:
        by_id_gap, children_gap, roots_gap, _ = _build_span_graph(spans)
        for rid in roots_gap:
            if not children_gap.get(rid):
                continue
            parent_dur = _get_duration_ms(by_id_gap[rid])
            child_merged = _merged_children_duration_ms(rid, by_id_gap, children_gap)
            if (
                parent_dur >= 1000.0
                and child_merged > 0
                and (child_merged / parent_dur) < 0.25
                and (parent_dur - child_merged) >= 1000.0
            ):
                has_time_gaps = True
                ratio = parent_dur / child_merged
                gap_ms = parent_dur - child_merged
                time_gap_note = (
                    f"Parent span wall-clock duration ({parent_dur:.0f}ms) is "
                    f"{ratio:.1f}x its child critical path ({child_merged:.0f}ms); "
                    f"unaccounted parent-child gap is {gap_ms:.0f}ms."
                )
                break

    headline = generate_headline(
        critical_path, errors, total_duration,
        critical_path_duration_ms=critical_path_duration,
        has_time_gaps=has_time_gaps,
    )

    deepest_error: Optional[TraceErrorSummary] = None
    error_origin_service: Optional[str] = None
    if errors:
        deepest_error = max(errors, key=lambda e: e.depth or 0)
        error_origin_service = deepest_error.service

    observation_codes: List[str] = []
    if errors:
        observation_codes.append("SPAN_ERRORS_PRESENT")
    if has_time_gaps:
        observation_codes.append("TRACE_TIME_GAPS")

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
        self_time_hotspots=self_time_hotspots,
        errors=errors,
        deepest_error_span=deepest_error,
        error_origin_service=error_origin_service,
        k8s_context=k8s_context if k8s_context else None,
        observation_codes=observation_codes,
    )
