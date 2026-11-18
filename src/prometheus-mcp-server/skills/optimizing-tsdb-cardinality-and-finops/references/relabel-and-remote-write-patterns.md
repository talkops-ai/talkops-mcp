# Relabeling, Remote-Write, and TSDB Capacity Architecture

## Table of Contents
1. [Scrape-Time vs. Write-Time Relabeling](#1-scrape-time-vs-write-time-relabeling)
2. [Canonical `metricRelabelings` Snippets (Prometheus Operator CRD)](#2-canonical-metricrelabelings-snippets-prometheus-operator-crd)
3. [Production `remote_write` Queue Tuning & Prometheus 3.0 Remote-Write 2.0](#3-production-remote_write-queue-tuning--prometheus-30-remote-write-20)
4. [TSDB Memory & Disk Capacity Sizing Formulas](#4-tsdb-memory--disk-capacity-sizing-formulas)
5. [High-Availability & Long-Term Storage Architecture Matrix](#5-high-availability--long-term-storage-architecture-matrix)

## 1. Scrape-Time vs. Write-Time Relabeling

| Config Block | Execution Point | Effect on Local TSDB | Effect on Remote Storage (Mimir/Thanos) |
| :--- | :--- | :--- | :--- |
| `relabel_configs` | Before scrape | Filters targets/pods before HTTP GET | Filtered targets are never scraped |
| `metric_relabel_configs` (`metricRelabelings` in CRD) | After scrape, **before** local TSDB ingestion | Reduces local RAM, WAL, and head series | Dropped series/labels never reach remote storage |
| `write_relabel_configs` | Before `remote_write` queue | Keeps full fidelity in local TSDB for short-term debugging | Reduces long-term cloud storage & network egress costs |

## 2. Canonical `metricRelabelings` Snippets (Prometheus Operator CRD)

### A. Drop High-Cardinality Labels (`labeldrop`)
> [!WARNING]
> Never `labeldrop` a label from a metric unless the remaining labels still uniquely identify each time series; otherwise, multiple series collide into identical label sets during the same scrape! If dropping `pod` or `instance`, use a **recording rule** instead.

```yaml
metricRelabelings:
  - action: labeldrop
    regex: "(request_id|session_id|user_id)"
```

### B. Drop Unused Expensive Metrics (`drop`)
```yaml
metricRelabelings:
  - sourceLabels: [__name__]
    regex: "(container_tasks_state|container_memory_failures_total|go_gc_duration_seconds)"
    action: drop
```

### C. Prune Unused Classic Histogram Buckets (`le`)
```yaml
metricRelabelings:
  - sourceLabels: [__name__, le]
    separator: ";"
    regex: "http_request_duration_seconds_bucket;(0\\.001|0\\.0025|15|30)"
    action: drop
```

## 3. Production `remote_write` Queue Tuning & Prometheus 3.0 Remote-Write 2.0
```yaml
remote_write:
  - url: https://mimir.example.com/api/v1/push
    send_native_histograms: true
    queue_config:
      capacity: 10000
      max_shards: 50
      min_shards: 1
      max_samples_per_send: 2000
      batch_send_deadline: 5s
    write_relabel_configs:
      - source_labels: [__name__]
        regex: "(job:.*|up|ALERTS|http_requests_total)"
        action: keep
```

## 4. TSDB Memory & Disk Capacity Sizing Formulas

When sizing a Prometheus instance from `prom://tsdb/cardinality` (`headStats.numSeries`):
- **Head-Block RAM Formula**:
  $$\text{Recommended RAM (bytes)} \approx \text{Active Series} \times 8\,\text{KB} \times 1.5\text{ (query + compaction headroom)}$$
  - Example: `1,000,000` active series $\rightarrow \approx 8\text{ GB}$ head block $\rightarrow$ provision **12–16 GiB RAM** pod limit.
- **Persistent Disk (SSD) Formula**:
  $$\text{Disk Bytes} \approx \text{Active Series} \times \frac{\text{Retention Seconds}}{\text{Scrape Interval Seconds}} \times 1.8\text{ bytes/sample} \times 1.25\text{ (WAL + compaction buffer)}$$
  - Example: `1,000,000` series at `30s` interval for `15d` retention (`43,200` samples/series) $\rightarrow \approx 97\text{ GB}$ SSD.

## 5. High-Availability & Long-Term Storage Architecture Matrix

| Scale (Active Series) | Recommended Architecture | Key Configuration Best Practices |
| :--- | :--- | :--- |
| `< 1.5M` series | **Single Prometheus** (or 2-replica HA pair) | Local SSD, `15d` retention, `wal-compression` enabled (default). |
| `1.5M – 10M` series | **Prometheus Operator Hashmod Sharding** (`spec.shards: N`) + **Thanos / Mimir** | Always pair sharding with `ThanosRuler` or Mimir Ruler so global aggregations (`sum by (job)`) evaluate across all shards. |
| `> 5M` series / Multi-Cluster | **Grafana Mimir / Thanos Receive / VictoriaMetrics** via `remote_write` | Set unique `external_labels: {cluster: "...", prometheus_replica: "..."}` for HA deduplication; keep local retention short (`24h–48h`) and tier long-term queries. |
