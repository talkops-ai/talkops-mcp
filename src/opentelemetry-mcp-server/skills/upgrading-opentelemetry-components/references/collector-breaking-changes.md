# OpenTelemetry Collector Breaking Changes Reference (`v0.100` – `v0.152+`)

## Table of Contents

1. [`logging` Exporter Removed -> Use `debug` Exporter](#1-logging-exporter-removed---use-debug-exporter)
2. [`memory_ballast` Extension Removed -> Use `GOMEMLIMIT` + `memory_limiter`](#2-memory_ballast-extension-removed---use-gomemlimit--memory_limiter)
3. [`service.telemetry.metrics.address` Removed -> Use `readers` Pull Schema](#3-servicetelemetrymetricsaddress-removed---use-readers-pull-schema)
4. [Semantic Conventions HTTP & Database Stabilization](#4-semantic-conventions-http--database-stabilization)
5. [Persistent Queue Storage via `file_storage` Extension](#5-persistent-queue-storage-via-file_storage-extension)

---

## 1. `logging` Exporter Removed -> Use `debug` Exporter

The legacy `logging` exporter was removed in OpenTelemetry Collector `v0.111.0`.
**Before (breaks startup)**:
```yaml
exporters:
  logging:
    loglevel: info
```
**After**:
```yaml
exporters:
  debug:
    verbosity: normal
```

---

## 2. `memory_ballast` Extension Removed -> Use `GOMEMLIMIT` + `memory_limiter`

The `memory_ballast` extension (`ballast_size_mib`) was removed in favor of the Go runtime's native `GOMEMLIMIT` environment variable (`Go 1.19+`).
- Remove `memory_ballast` from `extensions:` and `service.extensions:`.
- Set `GOMEMLIMIT` on the collector container to `80%` of the pod memory limit (configured automatically by `otel_provision_collector`).
- Keep `memory_limiter` as the **first** processor in every pipeline.

---

## 3. `service.telemetry.metrics.address` Removed -> Use `readers` Pull Schema

In Collector `v0.120.0+`, `service.telemetry.metrics.address: 0.0.0.0:8888` fails schema validation with `telemetry.metrics.address is not supported`.
**Before**:
```yaml
service:
  telemetry:
    metrics:
      address: 0.0.0.0:8888
```
**After**:
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

## 4. Semantic Conventions HTTP & Database Stabilization

Modern SDKs (`Java 2.x`, `Python 0.50b0+`, `Node.js 0.56+`, `.NET 1.10+`) emit stable HTTP and database semantic conventions:
- `http.method` -> `http.request.method`
- `http.status_code` -> `http.response.status_code`
- `http.url` -> `url.full`
- `net.peer.name` -> `server.address`

Ensure `spanmetrics.dimensions` and OTTL `filter`/`transform` statements reference `http.request.method`, `http.response.status_code`, and `url.path`.

---

## 5. Persistent Queue Storage via `file_storage` Extension

When enabling `sending_queue.storage: file_storage`, ensure `extensions.file_storage.directory` points to a writable persistent mount (`/var/lib/otelcol/file_storage`) provisioned on the `OpenTelemetryCollector` CR.
