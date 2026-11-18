"""TraceQL query building, hint decoration, continuation windowing, and validation utilities."""

from typing import Any, Dict, List, Optional

from tempo_mcp_server.models.search import SearchFilters

# Default K8s -> OTel attribute mapping (values do not include 'resource.' prefix)
DEFAULT_K8S_MAP: Dict[str, str] = {
    "namespace": "k8s.namespace.name",
    "service": "service.name",
    "deployment": "k8s.deployment.name",
    "cluster": "k8s.cluster.name",
    "environment": "deployment.environment",
}


def build_traceql_from_filters(
    filters: SearchFilters,
    k8s_map: Optional[Dict[str, str]] = None,
    http_status_attr: Optional[str] = None,
) -> str:
    """Convert normalized K8s search filters to a TraceQL query string.

    Args:
        filters: SearchFilters instance.
        k8s_map: Optional resource attribute map override.
        http_status_attr: Optional detected HTTP status attribute name
            (e.g. 'http.response.status_code' or 'http.status_code').
    """
    attr_map = k8s_map or DEFAULT_K8S_MAP
    predicates: List[str] = []

    def _resource_pred(key: str, default: str, value: str) -> str:
        attr = attr_map.get(key, default)
        assert not attr.startswith("resource."), (
            f"DEFAULT_K8S_MAP['{key}'] = '{attr}' must not start with 'resource.' "
            f"— the prefix is added at query-generation time. Use '{attr[9:]}' instead."
        )
        return f'resource.{attr} = "{value}"'

    # K8s / service filters
    if filters.namespace:
        predicates.append(_resource_pred("namespace", "k8s.namespace.name", filters.namespace))
    if filters.service:
        predicates.append(_resource_pred("service", "service.name", filters.service))
    if filters.deployment:
        predicates.append(_resource_pred("deployment", "k8s.deployment.name", filters.deployment))
    if filters.cluster:
        predicates.append(_resource_pred("cluster", "k8s.cluster.name", filters.cluster))
    if filters.environment:
        predicates.append(_resource_pred("environment", "deployment.environment", filters.environment))

    # Status filter
    if filters.status:
        st = filters.status.lower()
        if st in ("error", "ok", "unset"):
            predicates.append(f"status = {st}")

    # Duration filters
    if filters.min_duration_ms is not None:
        predicates.append(f"duration >= {filters.min_duration_ms}ms")
    if filters.max_duration_ms is not None:
        predicates.append(f"duration <= {filters.max_duration_ms}ms")

    # HTTP status filter
    if filters.http_status_gte is not None:
        target_attr = (http_status_attr or "http.status_code").lstrip(".")
        if target_attr.startswith("span."):
            predicates.append(f"{target_attr} >= {filters.http_status_gte}")
        else:
            predicates.append(f".{target_attr} >= {filters.http_status_gte}")

    # Span name filter
    if filters.span_name:
        predicates.append(f'name = "{filters.span_name}"')

    # Structural filters (Tempo 2.10+)
    if filters.leaf_spans_only:
        predicates.append("span:childCount = 0")
    if filters.min_child_spans is not None:
        predicates.append(f"span:childCount >= {filters.min_child_spans}")
    if filters.max_child_spans is not None:
        predicates.append(f"span:childCount <= {filters.max_child_spans}")

    # Attribute presence/absence
    if filters.missing_attributes:
        for attr in filters.missing_attributes:
            clean = attr if attr.startswith(("resource.", "span.", ".")) else f".{attr}"
            predicates.append(f"{clean} = nil")
    if filters.present_attributes:
        for attr in filters.present_attributes:
            clean = attr if attr.startswith(("resource.", "span.", ".")) else f".{attr}"
            predicates.append(f"{clean} != nil")

    if not predicates:
        return ""

    return "{ " + " && ".join(predicates) + " }"


def apply_query_hints(query: str, most_recent: bool = False) -> str:
    """Append TraceQL query hints such as with(most_recent=true) when requested."""
    if not query or not most_recent:
        return query
    if "most_recent" in query:
        return query
    return f"{query.strip()} with(most_recent=true)"


def compute_next_window(
    traces: List[Dict[str, Any]],
    resolved_start: Optional[float],
    resolved_end: Optional[float],
) -> Optional[Dict[str, float]]:
    """Compute deterministic continuation window [start, earliest_trace_epoch - 0.001]."""
    if not traces:
        return None

    earliest_sec: Optional[float] = None
    for t in traces:
        raw_ns = t.get("start_time") or t.get("startTimeUnixNano")
        if raw_ns is None:
            continue
        try:
            sec = int(raw_ns) / 1_000_000_000.0
            if sec > 0 and (earliest_sec is None or sec < earliest_sec):
                earliest_sec = sec
        except (ValueError, TypeError):
            continue

    if earliest_sec is None:
        return None

    next_end = round(earliest_sec - 0.001, 3)
    start_bound = round(resolved_start, 3) if resolved_start else round(next_end - 3600.0, 3)
    if next_end <= start_bound:
        return None
    return {"start": start_bound, "end": next_end}


_METRICS_AND_PIPELINE_FNS = (
    "rate(",
    "count_over_time(",
    "avg_over_time(",
    "sum_over_time(",
    "max_over_time(",
    "min_over_time(",
    "quantile_over_time(",
    "histogram_over_time(",
    "compare(",
    "topk(",
    "bottomk(",
)


def normalize_traceql_query(query: str) -> str:
    """Auto-wrap bare TraceQL predicates in { } braces if missing and normalize link:traceId -> link:traceID."""
    if not query or not query.strip():
        return query

    stripped = (
        query.strip()
        .replace("link:traceId", "link:traceID")
        .replace("link:spanId", "link:spanID")
    )

    if "{" in stripped or "}" in stripped:
        return stripped

    if any(fn in stripped for fn in _METRICS_AND_PIPELINE_FNS):
        return stripped

    _PREDICATE_SIGNALS = (
        "resource.", "span.", "status", "duration", "name",
        "=", "!=", ">", "<", "&&", "||", ".http.", ".rpc.",
        ".db.", "kind", "rootName", "rootServiceName",
        "traceDuration", "has(", "childCount", "trace:", "event.", "link.", "instrumentation.",
    )
    if any(signal in stripped for signal in _PREDICATE_SIGNALS):
        return "{ " + stripped + " }"

    return stripped


def validate_traceql_basic(query: str) -> Optional[str]:
    """Basic client-side TraceQL brace and selector validation."""
    if not query or not query.strip():
        return "Query is empty"

    stripped = query.strip()

    open_count = stripped.count("{")
    close_count = stripped.count("}")
    if open_count != close_count:
        return f"Mismatched braces: {open_count} opening vs {close_count} closing"

    if "{" not in stripped and "}" not in stripped:
        if not any(fn in stripped for fn in _METRICS_AND_PIPELINE_FNS):
            return "TraceQL queries must contain {} selectors or be metrics expressions"

    return None


def merge_traceql_queries(
    raw_query: Optional[str],
    generated_query: Optional[str],
) -> str:
    """Combine user-provided TraceQL with auto-generated filter query."""
    if raw_query and generated_query:
        raw = raw_query.strip()
        gen = generated_query.strip()

        if raw.startswith("{") and raw.endswith("}") and gen.startswith("{") and gen.endswith("}"):
            raw_inner = raw[1:-1].strip()
            gen_inner = gen[1:-1].strip()
            if not raw_inner:
                return gen
            if not gen_inner:
                return raw
            return "{ " + raw_inner + " && " + gen_inner + " }"

        return raw

    return raw_query or generated_query or ""
