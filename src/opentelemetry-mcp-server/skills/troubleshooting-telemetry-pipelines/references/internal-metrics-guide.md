# OpenTelemetry Collector Internal Metrics Guide (`:8888/metrics`)

## Table of Contents

1. [Collector v0.120+ Internal Telemetry Schema](#1-collector-v0120-internal-telemetry-schema)
2. [Receiver Health Metrics (`RT_RECEIVER_REFUSING_DATA`, `RT_ZERO_THROUGHPUT`)](#2-receiver-health-metrics-rt_receiver_refusing_data-rt_zero_throughput)
3. [Processor Backpressure Metrics](#3-processor-backpressure-metrics)
4. [Exporter & Queue Saturation Metrics (`RT_EXPORTER_DROPPING_DATA`, `RT_QUEUE_SATURATED`)](#4-exporter--queue-saturation-metrics-rt_exporter_dropping_data-rt_queue_saturated)
5. [Process Memory & Runtime Metrics (`RT_MEMORY_PRESSURE`)](#5-process-memory--runtime-metrics-rt_memory_pressure)

---

## 1. Collector v0.120+ Internal Telemetry Schema

In OpenTelemetry Collector `v0.120.0+` (including `0.152.1`), internal Prometheus metrics are configured under `service.telemetry.metrics.readers` rather than the removed legacy `service.telemetry.metrics.address` field:

```yaml
service:
  telemetry:
    metrics:
      level: detailed
      readers:
        - pull:
            exporter:
              prometheus:
                host: 0.0.0.0
                port: 8888
```

---

## 2. Receiver Health Metrics (`RT_RECEIVER_REFUSING_DATA`, `RT_ZERO_THROUGHPUT`)

| Prometheus Metric | Signal | Healthy Condition | Failure Trigger |
|---|---|---|---|
| `otelcol_receiver_accepted_spans` | Traces | Monotonically increasing | `== 0` with active traffic -> `RT_ZERO_THROUGHPUT` |
| `otelcol_receiver_refused_spans` | Traces | `== 0` | `> 0` -> `RT_RECEIVER_REFUSING_DATA` |
| `otelcol_receiver_accepted_metric_points` | Metrics | Monotonically increasing | `== 0` with active traffic -> `RT_ZERO_THROUGHPUT` |
| `otelcol_receiver_refused_metric_points` | Metrics | `== 0` | `> 0` -> `RT_RECEIVER_REFUSING_DATA` |
| `otelcol_receiver_accepted_log_records` | Logs | Monotonically increasing | `== 0` with active traffic -> `RT_ZERO_THROUGHPUT` |
| `otelcol_receiver_refused_log_records` | Logs | `== 0` | `> 0` -> `RT_RECEIVER_REFUSING_DATA` |

When `otelcol_receiver_refused_* > 0`, the `memory_limiter` processor has tripped its soft/hard limit and is rejecting incoming batches at the receiver boundary so upstream SDKs can retry.

---

## 3. Processor Backpressure Metrics

| Prometheus Metric | Description | Action when `> 0` |
|---|---|---|
| `otelcol_processor_refused_spans` | Spans refused by `memory_limiter` | Increase collector memory limit + `memory_limiter.limit_mib` or reduce `batch.send_batch_max_size` |
| `otelcol_processor_refused_metric_points` | Metric points refused by `memory_limiter` | Filter high-cardinality metrics via `otel_configure_processing` |
| `otelcol_processor_refused_log_records` | Log records refused by `memory_limiter` | Drop noisy debug/healthcheck logs via `otel_configure_processing` |

---

## 4. Exporter & Queue Saturation Metrics (`RT_EXPORTER_DROPPING_DATA`, `RT_QUEUE_SATURATED`)

| Prometheus Metric | Formula / Threshold | Meaning |
|---|---|---|
| `otelcol_exporter_sent_*` | Accepted & delivered to backend | Healthy delivery counter |
| `otelcol_exporter_send_failed_*` | `> 0` -> `RT_EXPORTER_DROPPING_DATA` | Permanent backend rejection (400/401/403) or exhausted retries |
| `otelcol_exporter_enqueue_failed_*` | `> 0` -> `RT_EXPORTER_DROPPING_DATA` | Sending queue is full; new batches dropped before transmission |
| `otelcol_exporter_queue_size / otelcol_exporter_queue_capacity` | `> 0.80` -> `RT_QUEUE_SATURATED` | Downstream backend is slower than ingestion rate; increase `num_consumers` or `queue_size` |

---

## 5. Process Memory & Runtime Metrics (`RT_MEMORY_PRESSURE`)

- `otelcol_process_memory_rss`: Resident Set Size in bytes.
- If `otelcol_process_memory_rss / container_memory_limit_bytes > 0.85`, `otel_diagnose_collector` emits `RT_MEMORY_PRESSURE`.
- Always set `GOMEMLIMIT` to `80%` of the container memory limit and `memory_limiter.limit_mib` to `80%` of the container memory limit.
