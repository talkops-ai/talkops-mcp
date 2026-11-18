# Production Log Alerting and Recording Rule Patterns

## Table of Contents
1. [Symptom-Based Error Ratio Alerts](#1-symptom-based-error-ratio-alerts)
2. [Log Absence / Silent Failure Alerts (`absent_over_time`)](#2-log-absence--silent-failure-alerts-absent_over_time)
3. [High-Cost Dashboard Query -> Recording Rule Conversion](#3-high-cost-dashboard-query---recording-rule-conversion)
4. [Anti-Flapping and Cardinality Safeguards](#4-anti-flapping-and-cardinality-safeguards)

---

## 1. Symptom-Based Error Ratio Alerts

Avoid alerting on raw `count_over_time(...[1m]) > 1` unless the event is a fatal crash or security breach. Instead, alert on the **error rate relative to total log volume** protected against divide-by-zero (`> 0` on the denominator—note that `clamp_min()` is PromQL-only and invalid in LogQL!) combined with a minimum volume floor:

```logql
(
  (
    sum by (service_name, namespace) (
      rate({service_name="payment", namespace="prod"} |= "ERROR" [5m])
    )
    /
    (
      sum by (service_name, namespace) (
        rate({service_name="payment", namespace="prod"} [5m])
      ) > 0
    )
  ) > 0.05
)
and
(
  sum by (service_name, namespace) (
    count_over_time({service_name="payment", namespace="prod"} |= "ERROR" [5m])
  ) >= 25
)
```

---

## 2. Log Absence / Silent Failure Alerts (`absent_over_time`)

Detect when a critical telemetry pipeline or service stops emitting logs altogether:

```logql
absent_over_time({service_name="payment", namespace="prod"}[15m]) == 1
```
- Always set `for: 5m` on `absent_over_time` rules to avoid false positives during brief network partitions.

---

## 3. High-Cost Dashboard Query -> Recording Rule Conversion

When Grafana dashboards compute `rate()` or `quantile_over_time()` across high-throughput JSON logs over `6h` or `24h` windows, convert the query into a `1m` Loki Ruler **recording rule** written to Prometheus (`remote_write`):

- **Record Name**: `namespace_service_route:loki_http_duration_seconds:p99_5m`
- **Expression**:
  ```logql
  quantile_over_time(0.99,
    {namespace="prod", service_name="api"}
      |= "duration_seconds"
      | json duration_seconds="duration_seconds", route="route"
      | unwrap duration_seconds
      | __error__="" [5m]
  ) by (namespace, service_name, route)
  ```

---

## 4. Anti-Flapping and Cardinality Safeguards

1. **Never include high-cardinality labels in `by (...)`**: Do not group alerts or recording rules by `pod_ip`, `trace_id`, `request_id`, or `user_id`.
2. **Always include `severity` and `service_name` labels** on alerting rules for Alertmanager routing.
3. **Always include `summary` and `description` annotations** with `{{ $labels.service_name }}` and `{{ $value }}`.
