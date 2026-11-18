# Cross-Pillar Correlation Guide (Logs <-> Metrics <-> Traces)

## Table of Contents
1. [Shared OpenTelemetry Resource Attributes](#1-shared-opentelemetry-resource-attributes)
2. [Pivoting from Metrics to Loki Logs](#2-pivoting-from-metrics-to-loki-logs)
3. [Pivoting from Loki Logs to Distributed Traces](#3-pivoting-from-loki-logs-to-distributed-traces)
4. [Pivoting from Distributed Traces Back to Loki Logs](#4-pivoting-from-distributed-traces-back-to-loki-logs)

---

## 1. Shared OpenTelemetry Resource Attributes

Modern Grafana observability stacks align labels across Prometheus, Loki 3.x, and Tempo using OpenTelemetry semantic conventions:

| OTel Attribute | Loki Indexed Label / Structured Metadata | Purpose |
|----------------|------------------------------------------|---------|
| `service.name` | `service_name` (indexed label) | Primary workload identity |
| `service.namespace` / `k8s.namespace.name` | `namespace` (indexed label) | Environment / boundary |
| `k8s.pod.name` | `pod` (indexed label or structured metadata) | Instance isolation |
| `trace_id` | `trace_id` (structured metadata) | Distributed trace correlation |
| `span_id` | `span_id` (structured metadata) | Span-level precision |

---

## 2. Pivoting from Metrics to Loki Logs

When a metric alert fires (e.g., high HTTP 5xx rate or p99 latency spike on `service_name="checkout"` between `14:00Z` and `14:15Z`):
1. Extract the exact label set (`service_name`, `namespace`, `cluster`) and the anomalous time window (`start="2025-05-01T14:00:00Z"`, `end="2025-05-01T14:15:00Z"`).
2. If the Prometheus histogram includes an exemplar `trace_id`, pass that `trace_id` directly to `loki_correlate_trace_logs`.
3. Otherwise, run `loki_summarize_service_logs` and `loki_compare_periods` over the exact alert window to identify the error signature responsible for the metric spike.

---

## 3. Pivoting from Loki Logs to Distributed Traces

When `loki_summarize_service_logs` or `loki_query_range` returns error lines containing a `trace_id` (either in structured metadata or inside the JSON/logfmt payload):
1. Call `loki_correlate_trace_logs(correlation_id="<trace_id>")` to gather all logs emitted across every service for that trace.
2. Hand off the `trace_id` to your distributed tracing workflow (Grafana Tempo) to inspect span waterfall durations, retries, and DB/gRPC span attributes.

---

## 4. Pivoting from Distributed Traces Back to Loki Logs

When a trace waterfall shows a failing span in a downstream service (e.g., `service.name="inventory-service"`, `span_id="a1b2c3d4e5f60718"`):
1. Call `loki_correlate_trace_logs(correlation_id="<trace_id>", scope_selector='{service_name="inventory-service"}')` to retrieve the exact application stack trace and structured log fields emitted during that span.
2. If the trace ID was not propagated into logs, query `loki_query_range` using `{service_name="inventory-service"}` within a `±5s` window around the failing span's timestamp.
