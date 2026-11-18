# Service-Graph and Span-Metrics Schema Reference

## 1. Tempo `metrics-generator` Processor Series

When `service-graphs` and `span-metrics` are enabled in `metrics_generator.processors` (or per-tenant via `tempo_patch_tenant_overrides`), Tempo remote-writes the following Prometheus series:

### Service-Graph Metrics (`service-graphs` processor)
- `traces_service_graph_request_total{client, server, connection_type}`: Total client-to-server calls.
- `traces_service_graph_request_failed_total{client, server, connection_type}`: Failed client-to-server calls.
- `traces_service_graph_request_server_seconds_bucket{client, server, le}`: Server-side duration histogram.
- `traces_service_graph_request_client_seconds_bucket{client, server, le}`: Client-observed duration histogram.
- `traces_service_graph_unpaired_spans_total{client, server}`: Client or server spans missing their peer span (indicates instrumentation gaps or dropped spans).

### Span-Metrics (`span-metrics` processor)
- `traces_spanmetrics_calls_total{service, span_name, span_kind, status_code}`: Total spans by service, operation, kind, and status (`STATUS_CODE_ERROR`, `STATUS_CODE_OK`, `STATUS_CODE_UNSET`).
- `traces_spanmetrics_latency_bucket{service, span_name, span_kind, le}`: Latency histogram in seconds.

## 2. Blast Radius & Edge Risk Heuristics

Given `edges` from `tempo_get_service_dependencies`:
- **Failing Dependency Edge**: `error_rate / max(call_rate, 0.0001) >= 0.02` (2% edge failure ratio).
- **High-Coupling Bottleneck**: A downstream node appears as `server` for `>= 3` distinct `client` services with `call_rate >= 10.0` req/s.
