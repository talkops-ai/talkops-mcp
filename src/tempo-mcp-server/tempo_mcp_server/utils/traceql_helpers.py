"""TraceQL query building and validation utilities.

Translates normalized K8s filters to TraceQL predicates.
Validated structural operators per Tempo 2.10+:
  - span:childCount for fan-out analysis
  - = nil / != nil for attribute presence checks
"""

from typing import Dict, List, Optional

from tempo_mcp_server.models.search import SearchFilters

# Default K8s → OTel attribute mapping
# NOTE: values here must NOT include the "resource." prefix — that is added
# at query-generation time via the `resource.{attr}` f-string below.
# Exception: "service" maps to "service.name" (not "resource.service.name")
# so that it produces `resource.service.name` — the canonical TraceQL form.
DEFAULT_K8S_MAP: Dict[str, str] = {
    "namespace": "k8s.namespace.name",
    "service": "service.name",           # resource. prefix added at gen-time
    "deployment": "k8s.deployment.name",
    "cluster": "k8s.cluster.name",
    "environment": "deployment.environment",
}


def build_traceql_from_filters(
    filters: SearchFilters,
    k8s_map: Optional[Dict[str, str]] = None,
) -> str:
    """Convert normalized K8s search filters to a TraceQL query string.

    Examples:
        namespace="prod" → { resource.k8s.namespace.name = "prod" }
        leaf_spans_only=True → { span:childCount = 0 }
        missing_attributes=["http.status_code"] → { .http.status_code = nil }
    """
    attr_map = k8s_map or DEFAULT_K8S_MAP
    predicates: List[str] = []

    def _resource_pred(key: str, default: str, value: str) -> str:
        """Build a resource-scoped predicate, guarding against double-prefixing.

        M-05: Asserts that map values never include the 'resource.' prefix,
        which is added here. A bad value like 'resource.service.name' would
        produce 'resource.resource.service.name' — broken TraceQL.
        """
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
        if filters.status.lower() == "error":
            predicates.append("status = error")
        elif filters.status.lower() == "ok":
            predicates.append("status = ok")
        elif filters.status.lower() == "unset":
            predicates.append("status = unset")

    # Duration filters
    if filters.min_duration_ms is not None:
        predicates.append(f"duration >= {filters.min_duration_ms}ms")
    if filters.max_duration_ms is not None:
        predicates.append(f"duration <= {filters.max_duration_ms}ms")

    # HTTP status filter
    if filters.http_status_gte is not None:
        predicates.append(f".http.status_code >= {filters.http_status_gte}")

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
            predicates.append(f".{attr} = nil")
    if filters.present_attributes:
        for attr in filters.present_attributes:
            predicates.append(f".{attr} != nil")

    if not predicates:
        return ""

    return "{ " + " && ".join(predicates) + " }"


def normalize_traceql_query(query: str) -> str:
    """Auto-wrap bare TraceQL predicates in { } braces if missing.

    LLMs frequently omit the required `{ }` selector braces, sending queries
    like `resource.service.name = "api" && status = error` instead of the
    correct `{ resource.service.name = "api" && status = error }`.

    This function detects bare predicates and wraps them automatically as a
    defense-in-depth measure.  It does NOT modify queries that already contain
    braces or are metrics expressions.

    Returns:
        The (possibly wrapped) query string.
    """
    if not query or not query.strip():
        return query

    stripped = query.strip()

    # Already has braces — leave as-is
    if "{" in stripped or "}" in stripped:
        return stripped

    # Metrics expressions don't need wrapping at this level
    _METRICS_FNS = (
        "rate(", "count_over_time(", "avg_over_time(",
        "sum_over_time(", "max_over_time(",
        "min_over_time(", "quantile_over_time(",
        "histogram_over_time(",
    )
    if any(fn in stripped for fn in _METRICS_FNS):
        return stripped

    # Looks like bare predicates — wrap them
    # Heuristic: contains TraceQL operators/keywords that belong inside { }
    _PREDICATE_SIGNALS = (
        "resource.", "span.", "status", "duration", "name",
        "=", "!=", ">", "<", "&&", "||", ".http.", ".rpc.",
        ".db.", "kind", "rootName", "rootServiceName",
        "traceDuration", "has(", "childCount",
    )
    if any(signal in stripped for signal in _PREDICATE_SIGNALS):
        return "{ " + stripped + " }"

    return stripped


def validate_traceql_basic(query: str) -> Optional[str]:
    """Basic client-side TraceQL validation.

    Returns error message if invalid, None if basic checks pass.
    Does NOT fully validate TraceQL syntax (server-side validation is authoritative).

    Note: Call ``normalize_traceql_query()`` BEFORE this function to auto-wrap
    bare predicates.  This validator assumes the query has already been
    through normalization.
    """
    if not query or not query.strip():
        return "Query is empty"

    stripped = query.strip()

    # Check matching braces
    open_count = stripped.count("{")
    close_count = stripped.count("}")
    if open_count != close_count:
        return f"Mismatched braces: {open_count} opening vs {close_count} closing"

    # Check for at least one brace pair for trace-level queries
    if "{" not in stripped and "}" not in stripped:
        # Could be a metrics query wrapping a selector
        if not any(fn in stripped for fn in ["rate(", "count_over_time(", "avg_over_time(",
                                               "sum_over_time(", "max_over_time(",
                                               "min_over_time(", "quantile_over_time(",
                                               "histogram_over_time("]):
            return "TraceQL queries must contain {} selectors or be metrics expressions"

    return None


def merge_traceql_queries(
    raw_query: Optional[str],
    generated_query: Optional[str],
) -> str:
    """Combine user-provided TraceQL with auto-generated filter query.

    If both are provided, combines using &&.
    """
    if raw_query and generated_query:
        # Extract predicates from both and combine
        raw = raw_query.strip()
        gen = generated_query.strip()

        # If raw is a full selector and generated is too, combine inner predicates
        if raw.startswith("{") and raw.endswith("}") and gen.startswith("{") and gen.endswith("}"):
            raw_inner = raw[1:-1].strip()
            gen_inner = gen[1:-1].strip()
            return "{ " + raw_inner + " && " + gen_inner + " }"

        # Fallback: just use raw query (user-provided takes priority)
        return raw

    return raw_query or generated_query or ""
