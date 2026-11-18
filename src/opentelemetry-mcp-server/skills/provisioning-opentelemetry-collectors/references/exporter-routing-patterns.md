# Exporter Routing, Queueing, and TLS Patterns

## Table of Contents
1. [Backend-to-Exporter Mapping](#backend-to-exporter-mapping)
2. [Resiliency Defaults (Queue & Retry)](#resiliency-defaults-queue--retry)
3. [TLS & Secret Reference Hygiene](#tls--secret-reference-hygiene)

## Backend-to-Exporter Mapping

| Backend Target | Signal | Recommended Exporter Key | Protocol / Endpoint Pattern |
|---|---|---|---|
| Jaeger / Tempo / Generic OTLP | `traces`, `metrics`, `logs` | `otlp/{signal}` | `host:4317` (gRPC) |
| Generic OTLP HTTP | `traces`, `metrics`, `logs` | `otlphttp/{signal}` | `http(s)://host:4318` |
| Prometheus / Mimir / VictoriaMetrics | `metrics` | `prometheusremotewrite/{signal}` | `http(s)://host:9090/api/v1/write` |
| Grafana Loki ($\ge 3.0$) | `logs` | `otlphttp/loki` | `http(s)://loki:3100/otlp` |
| OpenSearch | `traces`, `logs` | `opensearch/{signal}` | `https://opensearch:9200` |

> [!IMPORTANT]
> The legacy `loki` exporter is deprecated (`CFG_DEPRECATED_COMPONENT`). Always use `otlphttp/loki` targeting Loki's native `/otlp` ingestion endpoint.

## Resiliency Defaults (Queue & Retry)

Every production network exporter must configure bounded `sending_queue` and `retry_on_failure` (`CFG_NO_SENDING_QUEUE` / `CFG_NO_RETRY` prevention):

```yaml
exporters:
  otlp/traces:
    endpoint: tempo.observability.svc:4317
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 1000
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s
```

## TLS & Secret Reference Hygiene

- **Cluster-Internal HTTP vs External HTTPS**:
  - Plain `http://` or cluster-local gRPC (`*.svc.cluster.local:4317`) uses `tls.insecure: true`.
  - Any `https://` endpoint defaults to `tls.insecure: false` and `tls.insecure_skip_verify: false` (`SEC_TLS_VERIFY_DISABLED` prevention).
- **Zero Inline Secrets (`SEC_INLINE_SECRET`)**:
  - Never embed raw bearer tokens, API keys, or basic auth passwords in `headers.Authorization`.
  - Reference Kubernetes Secrets via `credentials_secret_refs` in `otel_provision_collector` and `${env:OTEL_BACKEND_TOKEN}` in the exporter header.
