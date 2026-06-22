# Label Governance Guide

Best practices for Loki label naming, cardinality management,
and structured metadata usage.

## Label Naming Conventions

### DO use as index labels (inside `{}` selectors)
Low-cardinality, stable dimensions:
- `namespace` — Kubernetes namespace
- `app` / `service_name` — Application identifier
- `cluster` — Cluster name
- `environment` / `env` — prod, staging, dev
- `region` — Cloud region
- `team` — Owning team
- `level` — Log level (info, warn, error, debug)
- `job` — Scrape job name

### DO NOT use as index labels
High-cardinality values cause index explosion:
- `trace_id`, `traceID` — Use structured metadata or `|=` filter
- `span_id`, `spanID` — Use structured metadata or `|=` filter
- `user_id`, `userId` — Use structured metadata or `| json | user_id="X"`
- `request_id`, `requestID` — Use structured metadata
- `order_id`, `orderId` — Use structured metadata
- `ip`, `ip_address` — Use structured metadata
- `session_id` — Use structured metadata
- `correlation_id` — Use structured metadata
- `message`, `msg` — Part of log line, never a label

## Cardinality Rules

### Golden Rule
**If a label has more than 10,000 unique values, it must NOT
be an index label.** Use structured metadata instead.

### Cardinality Tiers

| Tier | Unique Values | Strategy |
|------|--------------|----------|
| Low  | < 100 | Safe as index label |
| Medium | 100 - 10,000 | Acceptable but monitor growth |
| High | > 10,000 | MUST use structured metadata |
| Extreme | > 100,000 | Consider log line content only |

### Monitoring Cardinality
1. Use `get_active_series` with your selector
2. Check the `label_cardinality` field in the response
3. Labels exceeding the threshold will appear in `warnings`

## Structured Metadata Usage

Structured metadata allows filtering without index pollution:

```yaml
# In your log pipeline (e.g., Promtail, Alloy)
pipeline_stages:
  - structured_metadata:
      trace_id:
      user_id:
      request_id:
```

### Querying structured metadata
```logql
{app="checkout"} | trace_id="abc123"
{app="api"} | user_id="user-42" | level="error"
```

## Label Naming Standards

1. **Use snake_case**: `service_name`, not `serviceName`
2. **Be specific**: `http_status_code`, not `status`
3. **Avoid abbreviations**: `environment`, not `env` (exception: well-known)
4. **Prefix vendor labels**: `k8s_pod_name`, `aws_region`
5. **Use consistent naming** across all services

## Anti-Patterns

❌ `{trace_id="abc123"}` — Cardinality explosion
✅ `{app="checkout"} | trace_id="abc123"` — Metadata filter

❌ `{ip="10.0.0.1"}` — Too many unique IPs
✅ `{app="nginx"} |= "10.0.0.1"` — Line filter

❌ `{msg="user logged in"}` — Infinite cardinality
✅ `{app="auth"} |= "user logged in"` — Line filter

❌ `{pod="checkout-deploy-abc123-xyz"}` — Pod names change
✅ `{app="checkout", namespace="prod"}` — Stable labels
