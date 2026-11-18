# PromQL 3.0 Syntax, Native Histograms, and Function Reference

## 1. Metric Types & Required Aggregations

| Metric Type | Suffix Convention | Canonical PromQL Pattern |
| :--- | :--- | :--- |
| **Counter** | `_total`, `_count`, `_sum`, `_bucket` | `sum by (job) (rate(http_requests_total{job="api"}[5m]))` |
| **Gauge** | `_bytes`, `_ratio`, `_info`, `_current` | `avg by (instance) (node_memory_MemAvailable_bytes)` or `avg_over_time(m[5m])` |
| **Classic Histogram** | `_bucket`, `_sum`, `_count` | `histogram_quantile(0.99, sum by (le, job) (rate(http_request_duration_seconds_bucket[5m])))` |
| **Native Histogram (Prom 3.0)** | No `_bucket` suffix | `histogram_quantile(0.99, sum by (job) (rate(http_request_duration_seconds[5m])))` |
| **Summary** | `quantile="..."` label | Do **not** average pre-computed quantiles across instances; use `_sum` / `_count` for mean latency. |

## 2. Prometheus 3.0 Enhancements

1. **UTF-8 Metric and Label Names**:
   - Metrics or labels containing dots, slashes, or hyphens (e.g., OpenTelemetry `http.server.request.duration`) can be queried directly inside braces:
     ```promql
     rate({"http.server.request.duration_count", "service.name"="checkout"}[5m])
     ```
2. **Native Histogram Functions**:
   - `histogram_quantile(phi, b)` — estimates $\phi$-quantile (`0 <= phi <= 1`) from native histogram series without requiring `le` labels.
   - `histogram_fraction(lower, upper, b)` — returns the fraction of observations between `lower` and `upper` (e.g., `histogram_fraction(0, 0.2, rate(http_request_duration_seconds[5m]))` for % of requests under 200ms).
   - `histogram_avg(b)` and `histogram_stddev(b)` — compute exact mean and standard deviation from native histograms.
3. **Range & Subquery Modifiers**:
   - `@` modifier pins evaluation to a specific Unix timestamp or `start()` / `end()`: `http_requests_total @ end()`.
   - Subquery syntax `expr[window:resolution]`: `max_over_time(rate(http_requests_total[5m])[1h:1m])`.

## 3. Vector Matching & Label Joins (`on`, `ignoring`, `group_left`)

When joining an application metric with an informational metadata series (such as `kube_pod_info` or `kube_pod_labels`):
```promql
sum by (namespace, pod, node) (
  rate(container_cpu_usage_seconds_total{namespace="prod"}[5m])
)
* on (namespace, pod) group_left (node)
kube_pod_info{namespace="prod"}
```
- Always deduplicate the one-side (`kube_pod_info`) with `max by (namespace, pod, node) (kube_pod_info)` if multiple targets scrape `kube-state-metrics`.
