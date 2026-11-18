---
name: mapping-tempo-topology-and-alerts
description: Maps upstream and downstream distributed service dependency graphs (`tempo_get_service_dependencies`) and generates Prometheus `span-metrics` (`traces_spanmetrics_*`) and `service-graphs` (`traces_service_graph_*`) SLO alerting rules from Grafana Tempo. Use when analyzing pre-maintenance blast radius, high-coupling bottlenecks, failing `client -> server` RPC edges, unpaired datastore spans (`peer_attributes`), or `/setup-monitoring --signals traces`. Do not use for OTel Collector connector pipelines (use tuning-sampling-and-trace-derived-metrics), native PromQL rule unit-testing/upsert (use authoring-and-testing-prometheus-rules), individual trace diffs (use investigating-tempo-latency-regressions), or TempoStack CR deployment (use operating-tempo-deployments-and-tenants).
---

# Mapping Tempo Topology and Alerts

## Preconditions

- Read `tempo://server/capabilities` and `tempo://deployment/overview` (and `commands/setup-monitoring.md` when invoked via `/setup-monitoring`) via MCP resources first to discover exact configured `backend_id` values (e.g. `backend_id="default"`—never pass a Kubernetes namespace like `"observability"` as `backend_id`!) and active `metrics_generator.processors` (`service-graphs`, `span-metrics`, `local-blocks`).
- Preserve strict `tenant` (`X-Scope-OrgID`) isolation on multi-tenant Tempo backends so staging/chaos traffic never contaminates production topology maps.

## Topology & Alerting Workflow Checklist

- [ ] **Step 1 — Discover Service Dependency Graph**: Call `tempo_get_service_dependencies(backend_id=..., since=..., service=..., sample_traces=..., tenant=...)` using a verified `backend_id` from `tempo://server/capabilities` (`"default"`). Always pass `service="<target_service>"` explicitly when mapping a specific service's pre-maintenance blast radius (or `service=None` only for cluster-wide call graphs).
- [ ] **Step 2 — Report & Interpret All Three Discovery Tiers (`source_used`)**: Always state `source_used` and, whenever `source_used != "prometheus"`, explicitly explain the full 3-tier topology discovery hierarchy (`prometheus` -> `traceql_metrics_plus_trace_dag` -> `traceql_search`):
  - `prometheus` (Tier 1): Precomputed `traces_service_graph_request_total` and `traces_service_graph_request_failed_total` series across 100% of ingested spans.
  - `traceql_metrics_plus_trace_dag` (Tier 2): Combines TraceQL Metrics `rate()` (`local-blocks`) with parent-child service DAG edges extracted from sampled OTLP traces.
  - `traceql_search` (Tier 3): Sampled trace parent-child DAG fallback when Prometheus service-graphs and `local-blocks` are unavailable (warn that low-QPS or conditional edges such as `email` or `quote` may be missed unless `sample_traces` is raised up to `50` or `service-graphs` + `remote_write` is enabled).
- [ ] **Step 3 — Assess Blast Radius, Unpaired Spans & High-Risk Edges**:
  - Consult [service-graph-and-spanmetrics.md](references/service-graph-and-spanmetrics.md) to flag **High-Coupling Bottlenecks** (`>= 3` distinct upstream `client` callers with `call_rate >= 10.0` req/s) and **Failing Dependency Edges** (`error_rate / call_rate >= 0.02`), drilling into degraded downstream services with `tempo_analyze_service_red(..., group_by="span:name")`.
  - Whenever `traces_service_graph_unpaired_spans_total` is elevated, always address both root causes: (1) uninstrumented datastores/external endpoints (`postgresql`, `valkey-cart`) that emit no `SPAN_KIND_SERVER` spans—configure `peer_attributes` (`server.address`, `db.system`, `db.name`, `net.peer.name`, `peer.service`) under `metrics_generator.processor.service_graphs` to materialize virtual nodes—and (2) internal application microservices (`quote`, `email`, etc.) missing `SERVER` spans due to disabled OTel instrumentation (`otel.enabled=false`) or stripped W3C `traceparent` headers.
- [ ] **Step 4 — Measure Target Service RED Baseline & Verify Metric Naming**:
  - Call `tempo_analyze_service_red` on the target service to calibrate alert thresholds against observed request rate, error ratio, and p99 latency.
  - Distinguish Tempo `metrics-generator` series (`traces_spanmetrics_calls_total`, `traces_spanmetrics_latency_bucket` in **seconds**, retaining `span_kind="SPAN_KIND_SERVER"` and `status_code="STATUS_CODE_ERROR"` in Tempo `span-metrics` `PrometheusRule` expressions—do not strip `span_kind="SPAN_KIND_SERVER"` if non-Tempo eBPF/OBI metrics share the same name) from OpenTelemetry Collector `spanmetrics` connector series (`traces_span_metrics_calls_total`, `traces_span_metrics_duration_milliseconds_bucket` in **milliseconds**) to prevent dead alerts or `1000x` unit bugs, and always explicitly recommend verifying exact active metric names and bucket units in the target Prometheus instance before deploying any `PrometheusRule`.
- [ ] **Step 5 — Generate Prometheus Alerting Rules**: `[GATE]`
  - If `--slo <pct>` (e.g. `/setup-monitoring ... --slo 99.9 --signals traces`) or explicit error/latency thresholds ARE provided in the request, immediately execute `scripts/generate_spanmetrics_prometheus_rule.py` (calibrated to the SLO error budget / observed p99 baseline) and output the rendered `monitoring.coreos.com/v1` `PrometheusRule` YAML manifest (confirming only before applying live to Kubernetes).
  - If neither `--slo` nor explicit error/latency thresholds were specified, propose calibrated `--error-ratio` and `--p99-seconds` values from the observed RED baseline and confirm target `namespace` and thresholds with the operator first.

## References & Offline Scripts

- Service-graph and span-metrics metric schema reference: [service-graph-and-spanmetrics.md](references/service-graph-and-spanmetrics.md)
- PrometheusRule alert templates for Tempo span-metrics and service-graphs: [alert-templates.md](references/alert-templates.md)
- Offline `PrometheusRule` YAML generator: `scripts/generate_spanmetrics_prometheus_rule.py`
