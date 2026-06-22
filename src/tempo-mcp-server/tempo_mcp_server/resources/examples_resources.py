"""Examples resource — common TraceQL queries."""

from tempo_mcp_server.resources.base import BaseResource


class ExamplesResources(BaseResource):
    """Static example queries resource."""

    def register(self, mcp_instance) -> None:  # type: ignore[no-untyped-def]

        @mcp_instance.resource(
            "tempo://examples/common-queries",
            name="tempo_common_queries",
            description="Common TraceQL and metrics query examples for quick reference",
            mime_type="text/markdown",
        )
        async def tempo_common_queries() -> str:
            return """# Common TraceQL Queries

## Service Exploration
```traceql
# All traces for a service
{ resource.service.name = "api-gateway" }

# Specific endpoint
{ resource.service.name = "api-gateway" && name = "GET /users" }
```

## Error Investigation
```traceql
# All errors
{ status = error }

# HTTP 5xx errors
{ .http.status_code >= 500 }

# Errors in a namespace
{ resource.k8s.namespace.name = "production" && status = error }
```

## Performance Analysis
```traceql
# Slow spans (>500ms)
{ duration > 500ms }

# Slow database queries
{ name =~ ".*SELECT.*" && duration > 100ms }

# Leaf spans only (no children — actual work, not waiting)
{ span:childCount = 0 && duration > 200ms }
```

## Structural Queries
```traceql
# Frontend calling a slow backend
{ resource.service.name = "frontend" } >> { resource.service.name = "backend" && duration > 1s }

# Missing expected attributes
{ resource.service.name = "api" && .http.status_code = nil }
```

## Metrics Queries
```traceql
# Error rate by service (for tempo_traceql_metrics_range)
{ status = error } | rate() | by(resource.service.name)

# P99 latency
{ resource.service.name = "api" } | quantile_over_time(duration, 0.99)

# Request count by HTTP method
{ .http.method != nil } | count_over_time() | by(.http.method)

# Duration histogram
{ resource.service.name = "api" } | histogram_over_time(duration)
```
"""
