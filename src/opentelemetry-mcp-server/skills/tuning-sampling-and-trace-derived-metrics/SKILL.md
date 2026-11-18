---
name: tuning-sampling-and-trace-derived-metrics
description: Configures head probabilistic sampling, two-tier trace-ID load-balanced tail sampling, and pre-sampling spanmetrics and servicegraph connectors on OpenTelemetry Collectors to preserve 100% accurate RED metrics and dependency topology while cutting trace ingestion costs. Use when reducing trace storage spend, retaining 100% of error and high-latency traces, sizing tail-sampling StatefulSets, or generating RED histograms and servicegraph metrics from spans. Do not use for OTTL PII masking or URL regex normalization (use controlling-telemetry-cardinality-and-noise), SDK Instrumentation CR workload injection (use instrumenting-kubernetes-workloads), querying Tempo service graphs or PrometheusRule alerts (use mapping-tempo-topology-and-alerts), or Tempo server tenant overrides (use operating-tempo-deployments-and-tenants).
---

# Tuning Sampling and Trace-Derived Metrics

## Preconditions

- Read `otel://server/capabilities` via MCP resources (preferring MCP over raw `kubectl` commands) to verify write permissions (`allow_write`) and enabled `pipeline` toolset.
- Read `otel://sampling/{namespace}/{collector}`, `otel://spanmetrics/{namespace}/{collector}`, `otel://collector/{namespace}/{name}`, and `otel://collector/{namespace}/{name}/config` to inspect existing sampling policies, connector wiring, deployment mode (`daemonset`, `deployment`, `statefulset`), and replica count.

## Sampling & Connector Workflow Checklist

- [ ] **Step 1 — Wire Pre-Sampling Connectors (`spanmetrics` & `servicegraph`) First**:
  - Always compute RED metrics (`calls`, `duration`) and service topology edges (`service_graph_request_total`) **before** tail sampling drops normal spans, or else derived request counts and error percentages become skewed.
  - Call `otel_configure_connectors` (`namespace`, `collector_name`, `connectors=["spanmetrics", "servicegraph"]`, `connector_options={"dimensions": ["http.request.method", "http.response.status_code"]}`, `dry_run=True`).
  - Consult `references/spanmetrics-and-servicegraph.md` for dimension cardinality limits and exemplar rules.
- [ ] **Step 2 — Select Sampling Strategy & Size Tail-Sampler Memory**:
  - Consult `references/sampling-decision-matrix.md` to choose between `probabilistic` head sampling and `tail` sampling.
  - **Hard Constraint (`CFG_TAIL_SAMPLING_NO_TRACE_AFFINITY`)**: Never configure `tail_sampling` on a `daemonset` collector or a multi-replica `deployment` without a `loadbalancing` exporter (`routing_key: traceID`) upstream.
  - Run `scripts/estimate_tail_sampling_capacity.py --spans-per-sec 20000 --avg-spans-per-trace 25 --decision-wait-sec 10` to calculate `num_traces`, memory MiB, and replica count.
- [ ] **Step 3 — Preview Connector & Sampling Mutations (`dry_run=True`)**:
  - Call `otel_configure_sampling` (`namespace`, `collector_name`, `strategy="tail"`, `sampling_options={"sample_rate": 0.10, "decision_wait": "10s", "num_traces": 50000, "has_load_balancing_exporter": True}`, `dry_run=True`) or run `scripts/render_tail_sampling_policies.py` for custom composite policies.
  - When asked to temporarily disable sampling (`strategy="none"`, 100% capture) during a live incident, warn about downstream Tempo `rate_limited` / storage spikes, preview with `otel_configure_sampling(..., strategy="none", dry_run=True)`, and **explicitly recommend restoring `tail` sampling immediately once incident trace capture finishes**.
  - `[GATE]` Present the capacity calculation, connector wiring, and unified diff to the user for approval before applying.
- [ ] **Step 4 — Apply & Verify Pipeline Health**:
  - Re-run `otel_configure_connectors` and `otel_configure_sampling` with `dry_run=False`.
  - Verify via `otel_diagnose_collector` that no `CFG_CONNECTOR_LOOP`, `CFG_TAIL_SAMPLING_ON_DAEMONSET`, or `RT_MEMORY_PRESSURE` findings are reported.

## Reference & Script Inventory

- `references/sampling-decision-matrix.md` — Architectural comparison of head vs. tail vs. composite sampling and two-tier trace-ID routing requirements.
- `references/spanmetrics-and-servicegraph.md` — Pre-sampling pipeline wiring for `spanmetrics` and `servicegraph` connectors, histogram buckets, and dimension caps.
- `scripts/estimate_tail_sampling_capacity.py` — Offline sizing calculator for `num_traces`, in-memory span buffer footprint, and collector replica count.
- `scripts/render_tail_sampling_policies.py` — Offline generator for `tail_sampling` policy blocks (errors, latency, healthcheck drop, and baseline ratio).
