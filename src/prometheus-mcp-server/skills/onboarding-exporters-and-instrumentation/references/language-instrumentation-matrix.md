# Application Language Instrumentation Matrix (Prometheus & OpenTelemetry)

## 1. Recommended SDKs by Language & Framework

| Language | Official Prometheus SDK | OpenTelemetry Metrics SDK | Framework Middleware & Auto-Instrumentation |
| :--- | :--- | :--- | :--- |
| **Python** | `prometheus-client` | `opentelemetry-sdk` + `opentelemetry-exporter-prometheus` | **FastAPI / Starlette**: `prometheus-fastapi-instrumentator`<br>**Django**: `django-prometheus`<br>**Flask**: `prometheus-flask-exporter`<br>*Note*: Set `PROMETHEUS_MULTIPROC_DIR` when running Gunicorn/Uvicorn with multiple worker processes. |
| **Go** | `github.com/prometheus/client_golang/prometheus` | `go.opentelemetry.io/otel/exporters/prometheus` | Expose `/metrics` via `promhttp.HandlerOpts{EnableOpenMetrics: true}` to support **exemplars**. |
| **Java / JVM** | `io.micrometer:micrometer-registry-prometheus` | `io.opentelemetry.javaagent:opentelemetry-javaagent` | **Spring Boot**: `spring-boot-starter-actuator` (`management.endpoints.web.exposure.include=prometheus`, path `/actuator/prometheus`). |
| **Node.js / TS** | `prom-client` | `@opentelemetry/exporter-prometheus` | **Express / Fastify / NestJS**: `express-prom-bundle` or `prom-client.collectDefaultMetrics()`. |
| **Rust** | `prometheus` or `metrics-exporter-prometheus` | `opentelemetry-prometheus` | **Axum / Actix-Web**: `axum-prometheus` (`PrometheusMetricLayer`). |
| **.NET (C#)** | `prometheus-net.AspNetCore` | `OpenTelemetry.Exporter.Prometheus.AspNetCore` | Call `app.UseHttpMetrics()` and `app.MapMetrics()` on port `8080`/`9090`. |

## 2. Enabling OpenMetrics & Trace Exemplars (`traceID`)

To enable `prom_query_exemplars` and seamless pivoting into `tempo-mcp-server`:
1. Serve `/metrics` with `Content-Type: application/openmetrics-text; version=1.0.0; charset=utf-8` (negotiated via `Accept` header).
2. Attach the active OpenTelemetry span context (`traceID` and `spanID`) when observing histogram latencies or incrementing error counters:
   - **Python (`prometheus-client`)**: `HISTOGRAM.observe(duration, exemplar={"traceID": trace_id, "spanID": span_id})`
   - **Go (`client_golang`)**: `observer.(prometheus.ExemplarObserver).ObserveWithExemplar(duration, prometheus.Labels{"traceID": traceID})`
   - **Java (`Micrometer` / Spring Boot 3+)**: Automatically attaches `trace_id` and `span_id` exemplars when `micrometer-tracing-bridge-otel` is on the classpath.

## 3. Python Gunicorn / Uvicorn Multi-Worker Pattern (`PROMETHEUS_MULTIPROC_DIR` + OpenMetrics)

When running multi-worker Python apps (`gunicorn -w 4` or `uvicorn --workers 4`), each forked worker has isolated memory, causing counters to jump backward unless aggregated via `PROMETHEUS_MULTIPROC_DIR` and served with `prometheus_client.openmetrics.exposition`:

```python
from flask import Response  # or FastAPI Response
from prometheus_client import CollectorRegistry, multiprocess
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST, generate_latest

# gunicorn.conf.py
def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)

# /metrics handler (serves application/openmetrics-text; version=1.0.0; charset=utf-8 for exemplars!)
def metrics():
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)
```

Mount `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc` on a RAM-backed `emptyDir: {medium: Memory}` volume and clean stale `.db` files on pod startup.
