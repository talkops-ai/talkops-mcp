# Prometheus Best Practices

## Counter Rule Enforcement

Counter metrics represent monotonically increasing values (e.g., total requests, bytes sent).
Querying a raw counter value is almost always meaningless — the absolute number has no operational significance.

**Always use `rate()` or `increase()` with counters:**
- `rate(http_requests_total[5m])` → requests per second over 5 minutes
- `increase(http_requests_total[1h])` → total requests in the last hour

The Prometheus MCP Server enforces this rule by default. Set `allow_raw_counters=true` to override.

## Downsampling for LLM Context Windows

Range queries can return thousands of data points per series. This is wasteful for LLM analysis.
The MCP server automatically downsamples to ~200 points per series using average-bucket strategy.

## Labeling Best Practices

- Use `job` for logical service names
- Use `namespace` for Kubernetes namespaces
- Use `environment` for env separation (prod, staging, dev)
- Avoid high-cardinality labels (user IDs, request IDs, UUIDs)

## Monitoring Third-Party Systems

Use official exporters instead of custom instrumentation for databases, web servers, etc.:
- PostgreSQL → `postgres_exporter`
- Redis → `redis_exporter`
- NGINX → `nginx_exporter`
- MongoDB → `mongodb_exporter`

## ServiceMonitor Best Practices

- Always include `release` label matching your Prometheus Operator installation
- Set appropriate `scrapeInterval` (default 30s is fine for most workloads)
- Use `metricRelabelings` to drop unnecessary metrics at ingest time
