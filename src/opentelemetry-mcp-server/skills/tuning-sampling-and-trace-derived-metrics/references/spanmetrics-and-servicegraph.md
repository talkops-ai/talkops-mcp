# Pre-Sampling `spanmetrics` & `servicegraph` Connectors Reference

## Table of Contents

1. [Why Connectors Must Run Before Tail Sampling](#1-why-connectors-must-run-before-tail-sampling)
2. [`spanmetrics` Connector Configuration & RED Metrics](#2-spanmetrics-connector-configuration--red-metrics)
3. [`servicegraph` Connector Configuration & Topology Edges](#3-servicegraph-connector-configuration--topology-edges)
4. [Dimension Cardinality Guardrails](#4-dimension-cardinality-guardrails)
5. [Preventing Connector Loops (`CFG_CONNECTOR_LOOP`)](#5-preventing-connector-loops-cfg_connector_loop)

---

## 1. Why Connectors Must Run Before Tail Sampling

Connectors act as an exporter in one pipeline (`traces`) and a receiver in another pipeline (`metrics`).
- If `spanmetrics` and `servicegraph` are wired into a `traces` pipeline **upstream** of `tail_sampling` (or in a separate pre-sampling `traces/in` pipeline), they observe 100% of spans and emit exact Request, Error, and Duration (RED) counters and histograms.
- Meanwhile, `tail_sampling` only forwards 5–10% of normal traces plus 100% of error/slow traces to trace storage.

---

## 2. `spanmetrics` Connector Configuration & RED Metrics

Configured via `otel_configure_connectors(namespace=..., collector_name=..., connectors=["spanmetrics"], connector_options={...})`:

```yaml
connectors:
  spanmetrics:
    histogram:
      explicit:
        buckets: [2ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s]
    dimensions:
      - name: http.request.method
      - name: http.response.status_code
      - name: k8s.namespace.name
    exemplars:
      enabled: true
    namespace: traces.span.metrics
```

Emitted metrics:
- `traces_span_metrics_calls_total`: Counter of span calls partitioned by `service.name`, `span.name`, `span.kind`, `status.code`, and configured dimensions.
- `traces_span_metrics_duration_milliseconds_bucket`: Latency histogram with trace exemplars linking directly to sampled trace IDs.

---

## 3. `servicegraph` Connector Configuration & Topology Edges

Configured via `otel_configure_connectors(namespace=..., collector_name=..., connectors=["servicegraph"], connector_options={...})`:

```yaml
connectors:
  servicegraph:
    latency_histogram_buckets: [10ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s]
    dimensions:
      - http.request.method
    store:
      ttl: 2s
      max_items: 10000
```

Emitted metrics (compatible with Grafana Service Graph & Tempo):
- `traces_service_graph_request_total` (`client`, `server`, `connection_type`)
- `traces_service_graph_request_failed_total`
- `traces_service_graph_request_server_seconds_bucket`
- `traces_service_graph_request_client_seconds_bucket`

---

## 4. Dimension Cardinality Guardrails

- Keep `dimensions` to **3 or fewer** bounded attributes (`http.request.method`, `http.response.status_code`, `rpc.grpc.status_code`).
- Never include unbounded attributes (`url.full`, `http.target`, `user.id`, `k8s.pod.uid`, `session.id`) in `spanmetrics.dimensions` or `servicegraph.dimensions`, as multiplicative series growth will OOM Prometheus and the collector.

---

## 5. Preventing Connector Loops (`CFG_CONNECTOR_LOOP`)

A connector must connect **distinct** signal pipelines (e.g., exporter in `traces` -> receiver in `metrics`) or distinct named sub-pipelines (`traces/ingress` -> `traces/egress`).
Wiring the same connector as both receiver and exporter in the identical pipeline creates an infinite feedback loop and is blocked by `otel_validate_collector_config` and `otel_patch_collector` with `CFG_CONNECTOR_LOOP`.
