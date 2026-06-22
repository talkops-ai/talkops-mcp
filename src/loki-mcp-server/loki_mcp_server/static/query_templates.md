# LogQL Query Templates

Common query patterns for Loki log analysis. Use these as building blocks
for constructing LogQL queries.

## Incident Response

### Find error logs for a service
```logql
{namespace="production", app="<APP>"} |= "error" | json | __error__ = "" | line_format "{{.level}} {{.msg}}"
```

### Error rate by service
```logql
sum(rate({namespace="production"} |= "error" [5m])) by (app)
```

### 5xx HTTP errors with details
```logql
{namespace="production", app="<APP>"} | json | __error__ = "" | status_code >= 500 | line_format "{{.method}} {{.path}} {{.status_code}} {{.latency}}"
```

### Latency outliers (p99 > threshold)
```logql
quantile_over_time(0.99, {app="<APP>"} | json | unwrap latency_ms | __error__ = "" [5m]) > 500
```

### Error rate percentage by service
```logql
sum(rate({app="<APP>"} |= "error" [5m]))
/
sum(rate({app="<APP>"} [5m]))
* 100
```

## Alerting

### Service stopped logging (no logs alert)
```logql
# Returns 1 when no logs are received in 10 minutes
absent_over_time({app="<APP>"}[10m]) == 1
```

### Error rate spike (absolute threshold)
```logql
# Alert when error rate exceeds 10 errors/sec
sum(rate({app="<APP>"} |= "error" [5m])) > 10
```

### Error percentage exceeds 5%
```logql
sum(rate({app="<APP>"} |= "error" [5m]))
/
sum(rate({app="<APP>"} [5m]))
> 0.05
```

### High log volume (noisy service)
```logql
# Alert when a service exceeds 1000 lines/sec
sum(rate({app="<APP>"}[5m])) > 1000
```

### Boolean error presence (for dashboards)
```logql
# Returns 1 if errors exist, 0 otherwise (no filtering)
count_over_time({app="<APP>"} |= "error" [5m]) > bool 0
```

## Debugging

### Search for trace ID across services
```logql
{namespace="production"} |= "<TRACE_ID>"
```

### Logs around a timestamp (±5 minutes)
```logql
# Use start/end API params or MCP tool params to set the time window:
#   start: <TIMESTAMP> - 5m
#   end:   <TIMESTAMP> + 5m
{app="<APP>"} | json | __error__ = ""
```

### Application startup sequence
```logql
{app="<APP>"} |~ "starting|initialized|ready" | line_format "{{.ts}} {{.msg}}"
```

### Connection/dependency errors
```logql
{app="<APP>"} |~ "connection refused|timeout|ECONNRESET|dial tcp" | json | __error__ = ""
```

### Compare current vs previous hour
```logql
# Current error rate
sum(rate({app="<APP>"} |= "error" [5m]))
# Previous hour (use offset)
sum(rate({app="<APP>"} |= "error" [5m] offset 1h))
```

## Kubernetes / OpenTelemetry

### Pod crash and restart indicators
```logql
{k8s_namespace_name="<NAMESPACE>"} |~ "OOMKilled|CrashLoopBackOff|BackOff|Error|panic"
```

### Cross-service error scan
```logql
{service_name=~".+"} |~ "(?i)error" | json | __error__ = ""
```

### gRPC export/connection errors
```logql
{service_name="<SERVICE>"} |~ "code = (Unavailable|Internal|DeadlineExceeded)" | json | __error__ = ""
```

### OTel Collector pipeline errors
```logql
{k8s_container_name="otc-container"} |~ "exporter|dropped|refused|timeout"
```

### Logs by detected severity level
```logql
sum(rate({service_name="<SERVICE>"}[5m])) by (detected_level)
```

## Audit & Compliance

### Authentication events
```logql
{app="auth-service"} | json | __error__ = "" | action =~ "login|logout|password_change|token_refresh"
```

### Configuration changes
```logql
{app="config-service"} | json | __error__ = "" | event_type = "config_change" | line_format "user={{.user}} key={{.key}} old={{.old_value}} new={{.new_value}}"
```

### Access to sensitive resources
```logql
{app="api-gateway"} | json | __error__ = "" | path =~ "/admin/.*|/internal/.*" | line_format "{{.method}} {{.path}} user={{.user}} status={{.status_code}}"
```

## Performance Analysis

### Top log producers (by volume)
```logql
topk(10, sum(rate({namespace="production"}[1h])) by (app))
```

### Top log producers (by bytes)
```logql
topk(10, sum(bytes_rate({namespace="production"}[1h])) by (app))
```

### Log throughput by level
```logql
sum(rate({app="<APP>"}[5m])) by (level)
```

### Slow queries (database)
```logql
{app="<APP>"} | json | __error__ = "" | duration_ms > 1000 | line_format "{{.query}} took {{.duration_ms}}ms"
```

### Average latency by route
```logql
avg_over_time(
  {app="<APP>"} | json | unwrap duration_ms | __error__ = "" [5m]
) by (route)
```

### Detect noisiest log patterns
```logql
topk(5, sum(count_over_time({app="<APP>"}[1h])) by (detected_level))
```

## Pattern-Based Queries

### Use pattern parser for structured extraction
```logql
{app="nginx"} | pattern "<ip> <_> <_> [<timestamp>] \"<method> <path> <_>\" <status> <bytes>" | status >= 400
```

### JSON + filter pipeline
```logql
{app="<APP>"} | json | __error__ = "" | level = "error" | line_format "{{.ts}} [{{.level}}] {{.msg}} err={{.error}}"
```

### Extract specific JSON fields only (better performance)
```logql
{app="<APP>"} | json status="http.status", method="http.method" | status >= 500
```

## Tips

- Always use `get_cluster_labels` first to discover valid label names
- Use `get_query_stats` before expensive queries to check cost
- Use `get_detected_fields` to discover JSON/logfmt field names
- Prefer `| json` or `| logfmt` over `| regexp` for structured logs
- Never put high-cardinality labels (trace_id, user_id) in `{}` selectors
- Add `| __error__ = ""` after parsers and `unwrap` to filter out parse failures
- Use `| json field1, field2` instead of bare `| json` when you only need specific fields
- Use `absent_over_time` for "no logs" alerting — it returns 1 when no logs match
