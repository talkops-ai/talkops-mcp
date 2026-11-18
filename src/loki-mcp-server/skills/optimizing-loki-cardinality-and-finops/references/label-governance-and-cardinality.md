# Loki Label Governance and Cardinality Guide

## Table of Contents
1. [Why High Cardinality Hurts Loki](#1-why-high-cardinality-hurts-loki)
2. [Label Classification Matrix](#2-label-classification-matrix)
3. [Migrating High-Cardinality Labels to Structured Metadata](#3-migrating-high-cardinality-labels-to-structured-metadata)

---

## 1. Why High Cardinality Hurts Loki

Loki groups logs into **streams** defined by the unique combination of all indexed stream labels (`{label1="v1", label2="v2", ...}`):
- Each active stream holds an in-memory chunk buffer (default target `1.5 MB` compressed) in the Ingester.
- If a label like `request_id` or `pod_ip` changes per request or pod restart, Loki flushes thousands of **tiny, under-filled chunks** (`< 4 KB`) to object storage.
- Tiny chunks cause:
  1. **Ingester OOMs** and `max_global_streams_per_user` / `max_streams_per_user` rejections.
  2. **10x–50x slower queries** due to millions of S3/GCS `GetObject` API calls.
  3. **Bloated TSDB index files**.

---

## 2. Label Classification Matrix

| Label Name | Max Expected Values | Where It Belongs |
|------------|--------------------|------------------|
| `cluster`, `region`, `env` | `2 - 20` | **Indexed Stream Label** (`{}`) |
| `namespace` | `5 - 200` | **Indexed Stream Label** (`{}`) |
| `service_name`, `app`, `job` | `10 - 1,000` | **Indexed Stream Label** (`{}`) |
| `level`, `severity_text` | `5 - 10` | **Indexed Stream Label** or **Structured Metadata** |
| `pod`, `node`, `instance`, `container` | `100 - 50,000` | **Structured Metadata** (Loki 3.x) |
| `trace_id`, `span_id`, `request_id` | Unbounded | **Structured Metadata** (with Bloom Filters enabled) |
| `user_id`, `tenant_id`, `session_id`, `ip` | Unbounded | **Structured Metadata** or JSON/logfmt payload |
| `timestamp`, `latency_ms`, `stacktrace` | Unbounded | **Log Line Payload ONLY** |

---

## 3. Migrating High-Cardinality Labels to Structured Metadata

### Grafana Alloy (`loki.process`)
```alloy
loki.process "demote_high_cardinality" {
  stage.structured_metadata {
    values = {
      pod        = "pod",
      trace_id   = "trace_id",
      request_id = "request_id",
    }
  }
  stage.label_drop {
    values = ["pod", "trace_id", "request_id"]
  }
  forward_to = [loki.write.default.receiver]
}
```

### Promtail (`pipeline_stages`)
```yaml
pipeline_stages:
  - structured_metadata:
      pod:
      trace_id:
      request_id:
  - labeldrop:
      - pod
      - trace_id
      - request_id
```
