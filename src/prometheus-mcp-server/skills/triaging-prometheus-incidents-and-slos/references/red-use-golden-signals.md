# RED and USE Golden Signals Reference

## 1. RED Method (Request-Driven Services)

Use `prom_analyze_service_red` for microservices, APIs, gateways, and RPC endpoints:

| Signal | Standard Prometheus (`prometheus_http`) | OpenTelemetry (`otel`) | Triage Heuristic |
| :--- | :--- | :--- | :--- |
| **Rate** (RPS) | `sum(rate(http_requests_total{job="$svc"}[5m]))` | `sum(rate(http_server_request_duration_seconds_count{job="$svc"}[5m]))` | Sudden drop $\ge 50\%$ indicates upstream routing failure or DNS/ingress drop. |
| **Errors** (%) | `sum(rate(http_requests_total{job="$svc",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="$svc"}[5m])) * 100` | `sum(rate(http_server_request_duration_seconds_count{job="$svc",http_response_status_code=~"5.."}[5m])) / ...` | Error ratio $\ge 1\%$ (`ELEVATED_ERROR_RATIO`) warrants immediate exemplar and dependency check. |
| **Duration** (p50/p95/p99) | `histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{job="$svc"}[5m])))` | `histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{job="$svc"}[5m])))` | If $p99 / p50 \ge 5.0$ (`HIGH_TAIL_LATENCY_SKEW`), tail latency is affecting a subset of requests/pods; inspect exemplars. |

## 2. USE Method (Infrastructure & Resource Saturation)

Use `prom_query_instant` or `prom_query_range` for nodes, containers, databases, and queues:

- **CPU Utilization & Throttling**:
  - Utilization: `sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="$ns",container!=""}[5m]))`
  - CFS Throttling Ratio: `sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{namespace="$ns"}[5m])) / sum by (pod) (rate(container_cpu_cfs_periods_total{namespace="$ns"}[5m]))`
- **Memory Working Set vs Limits**:
  - `container_memory_working_set_bytes{namespace="$ns"} / kube_pod_container_resource_limits{resource="memory",namespace="$ns"}`
- **Disk & Network Saturation**:
  - Node disk I/O saturation: `rate(node_disk_io_time_weighted_seconds_total[5m])`
