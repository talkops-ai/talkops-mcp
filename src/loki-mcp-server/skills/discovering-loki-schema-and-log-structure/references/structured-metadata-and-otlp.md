# Loki 3.x Structured Metadata and OpenTelemetry (OTLP) Guide

## Table of Contents
1. [Indexed Labels vs. Structured Metadata vs. Log Body](#1-indexed-labels-vs-structured-metadata-vs-log-body)
2. [Native OTLP Ingestion Mapping (`/otlp/v1/logs`)](#2-native-otlp-ingestion-mapping-otlpv1logs)
3. [Querying Structured Metadata in LogQL](#3-querying-structured-metadata-in-logql)
4. [Discovering Structured Metadata with `loki_get_detected_fields`](#4-discovering-structured-metadata-with-loki_get_detected_fields)

---

## 1. Indexed Labels vs. Structured Metadata vs. Log Body

Loki 3.x stores metadata across three tiers with very different cost and query characteristics:

| Tier | Where It Lives | Cardinality Target | How to Query in LogQL |
|------|----------------|--------------------|-----------------------|
| **Indexed Stream Labels** | TSDB Index | Low (`< 15` labels; `< 100k` active streams per tenant) | Inside `{service_name="api", namespace="prod"}` |
| **Structured Metadata** | Chunk header alongside log lines (not in TSDB index) | Medium to High (`pod`, `node`, `trace_id`, `span_id`, `user_id`) | Pipeline label filter **without** a parser: `\| trace_id="abc" \| k8s_pod_name="api-7d9"` |
| **Log Line Payload** | Compressed chunk body | Unlimited | Line filter (`\|= "abc"`) followed by parser (`\| json`, `\| logfmt`, `\| pattern`) |

---

## 2. Native OTLP Ingestion Mapping (`/otlp/v1/logs`)

When OpenTelemetry Collectors or Grafana Alloy send logs to Loki's native `/otlp/v1/logs` endpoint, Loki applies default attribute mappings:

1. **Default Indexed Stream Labels**:
   - `service.name` + `service.namespace` -> `service_name`
   - Selected low-cardinality resource attributes configured in `otlp_config.resource_attributes.attributes_config` (e.g., `deployment.environment`, `k8s.namespace.name`, `k8s.cluster.name`).
2. **Default Structured Metadata**:
   - `trace_id`, `span_id`, `severity_text`, `severity_number`, `flags`
   - Remaining OTel resource attributes (`k8s.pod.name`, `k8s.container.name`, `k8s.node.name`, `service.instance.id`, `host.name`)
   - Log record attributes (`http.request.method`, `http.response.status_code`, `url.path`).

---

## 3. Querying Structured Metadata in LogQL

Because structured metadata is already attached to each log entry as key-value pairs, you **do not need `| json` or `| logfmt`** to filter on it:

```logql
{service_name="checkout"}
  | severity_text = "ERROR"
  | trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
```

> **Note**: Do **not** place structured metadata keys inside `{}` stream selectors (`{trace_id="..."}` will return zero results). Always filter structured metadata after `{}` using `| key="value"`.

---

## 4. Discovering Structured Metadata with `loki_get_detected_fields`

Run `loki_get_detected_fields(query='{service_name="checkout"}', start="now-1h")` to inspect all fields present in the stream:
- Fields with `parser: ""` or `structured_metadata` indicate Loki 3.x structured metadata that can be queried directly via `| field="value"`.
- Fields with `parser: "json"` or `parser: "logfmt"` require `| json` or `| logfmt` before filtering.
