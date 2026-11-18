# OpenTelemetry Transformation Language (OTTL) Cookbook

## Table of Contents

1. [OTTL Context Hierarchy (`resource`, `scope`, `span`, `metric`, `datapoint`, `log`)](#1-ottl-context-hierarchy-resource-scope-span-metric-datapoint-log)
2. [Dropping Noisy Healthcheck & Readiness Spans (`filter` Processor)](#2-dropping-noisy-healthcheck--readiness-spans-filter-processor)
3. [Parsing JSON Log Bodies & Extracting `trace_id` / `span_id` (`transform` Processor)](#3-parsing-json-log-bodies--extracting-trace_id--span_id-transform-processor)
4. [Normalizing High-Cardinality URL Paths](#4-normalizing-high-cardinality-url-paths)
5. [Deleting Unbounded Attributes (`delete_key`, `delete_matching_keys`)](#5-deleting-unbounded-attributes-delete_key-delete_matching_keys)

---

## 1. OTTL Context Hierarchy (`resource`, `scope`, `span`, `metric`, `datapoint`, `log`)

Always set `error_mode: ignore` on production `transform` and `filter` processors so a single malformed log line or attribute type mismatch never drops an entire OTLP batch:

```yaml
processors:
  transform/sanitize:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          - delete_key(attributes, "http.request.header.authorization")
```

---

## 2. Dropping Noisy Healthcheck & Readiness Spans (`filter` Processor)

Configured automatically by `otel_configure_processing(drop_noise_paths=["/healthz", "/readyz", "/metrics"])`:

```yaml
processors:
  filter/drop_noise:
    error_mode: ignore
    traces:
      span:
        - 'attributes["url.path"] == "/healthz"'
        - 'attributes["url.path"] == "/readyz"'
        - 'attributes["url.path"] == "/livez"'
        - 'attributes["url.path"] == "/metrics"'
        - 'attributes["http.target"] == "/healthz"'
    logs:
      log_record:
        - 'IsMatch(body.string, "(?i)GET /(healthz|readyz|livez|metrics)")'
```

---

## 3. Parsing JSON Log Bodies & Extracting `trace_id` / `span_id` (`transform` Processor)

Never use `error_mode: propagate` in production: a single plaintext log line failing `ParseJSON` will abort and drop the entire OTLP batch! Always combine `error_mode: ignore` with an inline `where` JSON-object guard directly on the `ParseJSON` statement:

```yaml
processors:
  transform/json_logs:
    error_mode: ignore
    log_statements:
      - context: log
        statements:
          - merge_maps(attributes, ParseJSON(body.string), "upsert") where body.string != nil and IsMatch(body.string, "^\\{.*\\}$")
          - set(severity_text, attributes["level"]) where attributes["level"] != nil
          - set(trace_id.string, attributes["trace_id"]) where attributes["trace_id"] != nil
          - set(span_id.string, attributes["span_id"]) where attributes["span_id"] != nil
```

---

## 4. Normalizing High-Cardinality URL Paths

Replace dynamic UUIDs and numeric IDs in `url.path` using `replace_pattern`, **and always delete raw `url.full`, `url.query`, and legacy `http.target` attributes** across both spans and metrics (`drop_attributes: ["url.full", "url.query", "http.target"]`) so unnormalized paths and query `sessionId` parameters never leak into downstream labels:

```yaml
processors:
  transform/normalize_urls:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          - replace_pattern(attributes["url.path"], "/[0-9a-fA-F-]{36}", "/{uuid}")
          - replace_pattern(attributes["url.path"], "/[0-9]{4,}", "/{id}")
          - delete_key(attributes, "url.full")
          - delete_key(attributes, "url.query")
          - delete_key(attributes, "http.target")
```

---

## 5. Deleting Unbounded Attributes (`delete_key`, `delete_matching_keys`)

```yaml
processors:
  transform/drop_attrs:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          - delete_key(attributes, "url.query")
          - delete_key(attributes, "user_agent.original")
          - delete_matching_keys(attributes, "^http\\.request\\.header\\..*")
    metric_statements:
      - context: datapoint
        statements:
          - delete_key(attributes, "user.id")
          - delete_key(attributes, "session.id")
```

---

## 6. Processor Ordering Invariant (`memory_limiter` -> `transform`/`filter` -> `batch`)

Always enforce `[memory_limiter, k8sattributes, transform/*, filter/*, batch]`:
1. **`transform` before `memory_limiter` (OOM Risk)**: Running OTTL regex/JSON allocations before `memory_limiter` allows traffic spikes to exhaust Go heap memory and `OOMKill` the collector pod before `memory_limiter` can apply `429`/`ResourceExhausted` backpressure.
2. **`filter` after `batch` (Under-Filled Fragmented Batches)**: Running `filter` *after* `batch` wastes CPU assembling full batches only to strip items out afterward, emitting tiny under-filled/fragmented batches to Tempo, Loki, and Prometheus.
