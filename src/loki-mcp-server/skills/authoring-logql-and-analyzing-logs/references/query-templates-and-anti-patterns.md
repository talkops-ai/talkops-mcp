# Production LogQL Query Templates and Anti-Patterns

## Table of Contents
1. [Incident Investigation Templates](#1-incident-investigation-templates)
2. [SLO and Alerting Metric Templates](#2-slo-and-alerting-metric-templates)
3. [Kubernetes and OpenTelemetry Templates](#3-kubernetes-and-opentelemetry-templates)
4. [Security and Audit Templates](#4-security-and-audit-templates)
5. [High-Cost LogQL Anti-Patterns to Avoid](#5-high-cost-logql-anti-patterns-to-avoid)

---

## 1. Incident Investigation Templates

### Error Log Discovery with Noise Suppression
```logql
{service_name="checkout", namespace="prod"}
  |~ "(?i)(error|exception|fatal|panic)"
  != "context canceled"
  != "healthcheck"
```

### Trace ID Correlation (Loki 3.x Structured Metadata + Line Filter Fallback)
```logql
{namespace="prod"} |= "4bf92f3577b34da6a3ce929d0e0e4736" | json | __error__=""
```
Or when `trace_id` is stored in Loki 3.x structured metadata:
```logql
{service_name="checkout"} | trace_id="4bf92f3577b34da6a3ce929d0e0e4736"
```

### HTTP 5xx Error Breakdown by Route
```logql
sum by (route, status) (
  count_over_time(
    {service_name="api-gateway", namespace="prod"}
      |= "status"
      | json status="http.status_code", route="http.route"
      | status >= 500
      | __error__="" [5m]
  )
)
```

---

## 2. SLO and Alerting Metric Templates

### Error Ratio (5xx / Total Requests — Native LogQL Denominator Guard)
> Note: `clamp_min()` is PromQL-only and causes a parse error in LogQL. Always filter the denominator with `> 0`:
```logql
sum by (method) (rate({service_name="api", namespace="prod"} | json status="status", method="method" | status >= 500 | __error__="" [5m]))
/
(sum by (method) (rate({service_name="api", namespace="prod"} | json status="status", method="method" | __error__="" [5m])) > 0)
```

### p95 Request Latency from JSON Logs
```logql
quantile_over_time(0.95,
  {service_name="api", namespace="prod"}
    |= "duration_ms"
    | json duration_ms="duration_ms", route="route"
    | unwrap duration_ms
    | __error__="" [5m]
) by (route)
```

### Top 10 Noisiest Workloads by Ingestion Bytes/sec
```logql
topk(10,
  sum by (namespace, service_name) (
    bytes_rate({namespace=~".+"} [15m])
  )
)
```

---

## 3. Kubernetes and OpenTelemetry Templates

### CrashLoopBackOff / OOMKilled Signals in Application Logs
```logql
{namespace="prod"} |~ "(?i)(oom|out of memory|panic:|segfault|fatal error:)"
```

### OpenTelemetry Native OTLP Log Severity Filter
Loki 3.x maps OTel `SeverityText` and `service.name`:
```logql
{service_name="payment-service"} | severity_text=~"ERROR|FATAL" | trace_id != ""
```

---

## 4. Security and Audit Templates

### Authentication Failures by Source IP
```logql
topk(15,
  sum by (client_ip) (
    count_over_time(
      {service_name="auth-service"}
        |= "authentication failed"
        | json client_ip="client.ip"
        | __error__="" [15m]
    )
  )
)
```

---

## 5. High-Cost LogQL Anti-Patterns to Avoid

| Anti-Pattern | Why It Hurts | Production Fix |
|--------------|--------------|----------------|
| `{namespace="prod"} \| json \| msg =~ ".*timeout.*"` | Parses 100% of JSON logs in `prod` before filtering | `{namespace="prod"} \|= "timeout" \| json msg="msg"` |
| `{app=~".*"} \|= "error"` | Matches every stream in the cluster; triggers `max_query_series` error | Bound at least one exact label (`{namespace="prod", service_name="api"}`) |
| `quantile_over_time(0.99, {app="api"} \| json \| unwrap latency [5m])` | Fails entire query on a single non-JSON or missing-field line | Add `\|= "latency"` before `\| json` and `\| __error__=""` after `\| unwrap latency` |
| Using `\| regexp` for simple space-delimited logs | Regex engine allocates state per log line | Use `\| pattern` (`<ip> - <_> "<method> <path> <_>" <status>`) which is 5–10x faster |
| Placing `trace_id` or `user_id` inside `{trace_id="..."}` | High cardinality in `{}` causes index bloat or misses structured metadata | Use `{service_name="api"} \| trace_id="..."` or `\|= "<trace_id>"` |
