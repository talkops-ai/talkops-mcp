"""Static reference resources — TraceQL, metrics, K8s attributes, query policies."""

from tempo_mcp_server.resources.base import BaseResource


class ReferenceResources(BaseResource):
    """Static reference documentation loaded upfront."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        config = self.config

        @mcp_instance.resource(
            "tempo://reference/traceql",
            name="tempo_traceql_reference",
            description="TraceQL syntax reference: selectors, operators, intrinsics, structural queries, examples",
            mime_type="text/markdown",
        )
        async def tempo_traceql_reference() -> str:
            return """# TraceQL Quick Reference

## Selectors
- `{ <predicates> }` — Span selector (AND logic within braces)
- `{ } >> { }` — Ancestor/descendant (structural)
- `{ } ~ { }` — Sibling spans

## Intrinsics
- `duration` — Span duration (supports ms, s, m, h units)
- `name` — Span name (operation)
- `status` — Span status: `ok`, `error`, `unset`
- `kind` — Span kind: `server`, `client`, `producer`, `consumer`, `internal`
- `rootName` — Root span name
- `rootServiceName` — Root service name
- `traceDuration` — Total trace duration
- `span:childCount` — Number of child spans (Tempo 2.10+)

## Scoped Attributes
- `resource.<attr>` — Resource-level (e.g., `resource.service.name`)
- `span.<attr>` — Span-level (e.g., `span.http.status_code`)
- `.<attr>` — Unscoped (searches both resource and span)

## Operators
- `=`, `!=` — Equality
- `>`, `>=`, `<`, `<=` — Comparison (numeric/duration)
- `=~`, `!~` — Regex match
- `&&`, `||` — Logical AND, OR

## Nil Checks (Presence/Absence)
- `.attr = nil` — Attribute is absent
- `.attr != nil` — Attribute is present

## Examples
```
# Errors in a namespace
{ resource.k8s.namespace.name = "production" && status = error }

# Slow spans
{ duration > 500ms && resource.service.name = "api-gateway" }

# Leaf spans only (no children)
{ span:childCount = 0 && duration > 1s }

# Structural: client calling server
{ resource.service.name = "frontend" } >> { resource.service.name = "backend" }
```
"""

        @mcp_instance.resource(
            "tempo://reference/traceql-metrics",
            name="tempo_traceql_metrics_reference",
            description="TraceQL metrics functions: rate, count_over_time, quantile, histogram",
            mime_type="text/markdown",
        )
        async def tempo_traceql_metrics_reference() -> str:
            return """# TraceQL Metrics Reference

## Functions
- `rate()` — Per-second rate of matching spans
- `count_over_time()` — Count of matching spans per step
- `avg_over_time(attr)` — Average of a numeric attribute
- `max_over_time(attr)` — Maximum value
- `min_over_time(attr)` — Minimum value
- `sum_over_time(attr)` — Sum of values
- `quantile_over_time(attr, q)` — Quantile (0-1)
- `histogram_over_time(attr)` — Distribution histogram

## Grouping
- `| by(attr)` — Group by attribute
- `| by(resource.service.name)` — Common: group by service

## Aggregations
- `| topk(n)` — Top N series
- `| bottomk(n)` — Bottom N series

## Sampling (for large datasets)
- Sampling is handled automatically by the MCP server via the `TEMPO_DEFAULT_METRICS_SAMPLING` configuration.
- Do NOT append inline sampling syntax to the query string (e.g. `with(sampling=...)`) as it is invalid TraceQL.

## Examples
```
# Error rate by service
{ status = error } | rate() | by(resource.service.name)

# P99 latency for API service
{ resource.service.name = "api" } | quantile_over_time(duration, 0.99)

# Request count by HTTP method
{ .http.method != nil } | count_over_time() | by(.http.method)
```
"""

        @mcp_instance.resource(
            "tempo://reference/k8s-attributes",
            name="tempo_k8s_attributes_reference",
            description="Canonical K8s-to-Tempo attribute mapping for Kubernetes observability",
            mime_type="text/markdown",
        )
        async def tempo_k8s_attributes_reference() -> str:
            return """# K8s → Tempo Attribute Mapping

| K8s Concept | OTel Attribute | Example |
|---|---|---|
| Namespace | `k8s.namespace.name` | `production` |
| Pod | `k8s.pod.name` | `api-7b5f4d-x2k` |
| Deployment | `k8s.deployment.name` | `api-gateway` |
| ReplicaSet | `k8s.replicaset.name` | `api-7b5f4d` |
| Node | `k8s.node.name` | `node-pool-1-abc` |
| Cluster | `k8s.cluster.name` | `prod-us-east` |
| Container | `k8s.container.name` | `api` |
| Service | `resource.service.name` | `api-gateway` |
| Environment | `deployment.environment` | `production` |

## Usage in TraceQL
```
{ resource.k8s.namespace.name = "production" && resource.k8s.deployment.name = "api" }
```
"""

        @mcp_instance.resource(
            "tempo://reference/query-policies",
            name="tempo_query_policies_reference",
            description="Query guardrails, limits, continuation strategy, and safety guidelines",
            mime_type="text/markdown",
        )
        async def tempo_query_policies_reference() -> str:
            policy = config.query_policy
            return f"""# Query Policies & Safety

## Current Settings
- **Max lookback**: {policy.max_lookback}
- **Default search limit**: {policy.default_search_limit}
- **Max search limit**: {policy.max_search_limit}
- **Default SPSS**: {policy.default_spss}
- **Max SPSS**: {policy.max_spss}
- **Time range required**: {policy.require_time_range}
- **Filter/query required**: {policy.require_filter_or_query}

## Guidelines
1. Always start with a time range (even if relative: `since=1h`)
2. Use specific filters before broad searches
3. Start with low SPSS, increase only if needed
4. Tempo search is non-deterministic — repeated queries may return different traces
5. Tag value queries may be truncated by `max_bytes_per_tag_values_query` — narrow time range if values are missing

## Continuation Strategy
If a search is truncated:
1. Narrow the time range
2. Add more specific filters
3. Reduce the limit and iterate
"""
