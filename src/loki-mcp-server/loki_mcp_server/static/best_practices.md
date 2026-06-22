# Loki Best Practices

## 1. Label Cardinality

Labels are **indexed** in Loki. Every unique label combination creates a new stream.
High-cardinality labels (trace_id, user_id, IP) should NEVER be labels.

### Good Labels (Low Cardinality)
- `app`, `service`, `namespace`, `environment`
- `level` (info, warn, error, debug)
- `region`, `cluster`, `datacenter`
- `job`, `instance` (when bounded)

### Bad Labels (High Cardinality) — Use Structured Metadata Instead
- `trace_id`, `span_id`, `request_id`
- `user_id`, `session_id`, `order_id`
- `ip`, `ip_address`, `host`
- `path` (with dynamic segments like `/users/123`)

### How to Check
Use `analyze_loki_cardinality` to check unique values per label.
Labels with >10,000 unique values should be moved to structured metadata.

## 2. Structured Metadata

Loki supports structured metadata — key-value pairs attached to log entries
that are NOT part of the label index. They can be queried efficiently using
bloom filters.

```logql
# Query structured metadata (correct)
{app="checkout"} | trace_id = "abc123"

# WRONG — this creates a high-cardinality label
{app="checkout", trace_id="abc123"}
```

Use `search_loki_structured_metadata` for these lookups.

## 3. Pattern Parser Over Regexp

The `| pattern` parser is Loki's recommended approach for semi-structured logs.

```logql
# ✅ Pattern parser — fast, readable
{app="nginx"} | pattern "<ip> - - [<timestamp>] \"<method> <path> <_>\" <status> <bytes>"

# ❌ Regexp — slow, hard to read
{app="nginx"} | regexp "(?P<ip>\\S+) - - \\[(?P<timestamp>[^\\]]+)\\].*"
```

Use `query_loki_patterns` to discover patterns, then `suggest_loki_parser`
to generate the expression.

## 4. Query Pipeline Optimization

### Filter Early
Apply line filters (`|=`, `!=`) before parsers to reduce data volume:
```logql
# ✅ Good — line filter first
{app="checkout"} |= "error" | json

# ❌ Bad — parsing everything, then filtering
{app="checkout"} | json | level = "error"
```

### Use Specific Selectors
```logql
# ✅ Good — narrow selector
{app="checkout", namespace="prod"} |= "error"

# ❌ Bad — scanning everything
{namespace="prod"} |= "error"
```

## 5. Time Window Management

- Start with short windows (1h) and expand if needed
- Maximum recommended: 14 days
- Use `query_loki_stats` to estimate cost before long queries
- Use `query_loki_volume` to find which time periods have the most data

## 6. Metric Queries

For dashboards and alerting, use LogQL metric queries:
```logql
# Error rate per service
sum(rate({namespace="prod"} |= "error" [5m])) by (app)

# P99 latency from structured logs
quantile_over_time(0.99, {app="api"} | json | unwrap duration [5m]) by (endpoint)

# Log volume trend
sum(bytes_rate({namespace="prod"} [1h])) by (app)
```

Always specify a `step` parameter for metric queries to control resolution.
