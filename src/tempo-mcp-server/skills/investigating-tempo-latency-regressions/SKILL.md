---
name: investigating-tempo-latency-regressions
description: Investigates p50, p95, and p99 latency regressions in Grafana Tempo by comparing slow vs baseline trace cohorts, analyzing critical paths and merged-interval self-time hotspots, correlating async producer-consumer span links, and computing 5-axis structural trace diffs (`tempo_compare_traces`). Use when diagnosing slow endpoints, bimodal tail spikes, uniform latency shifts, N+1 database/RPC fan-out, async queue delays, or uninstrumented time gaps. Do not use for HTTP/gRPC error spikes (use triaging-tempo-service-errors), general TraceQL syntax authoring (use authoring-traceql-and-metrics-queries), service dependency topology/alerts (use mapping-tempo-topology-and-alerts), or OTel Collector tail-sampling configs (use tuning-sampling-and-trace-derived-metrics).
---

# Investigating Tempo Latency Regressions

## Preconditions

- Read `tempo://server/capabilities`, `tempo://system/backends`, and `tempo://system/backends/{backend_id}` via MCP resources to verify active backend features (`traceql_metrics`) before querying.
- Discover attribute names with `tempo_get_attribute_names` (`scope="resource"` and `scope="span"`) before filtering by route, pod, or deployment version.

## Latency Investigation Checklist

- [ ] **Step 1 — Measure Latency Quantiles & Shape**: Call `tempo_analyze_service_red` (`service`, `since`, `baseline_offset`, optional `group_by`) and classify the shift via [latency-heuristics.md](references/latency-heuristics.md): **Bimodal Tail Spike** (`p99 / p50 >= 5.0`) vs **Uniform Latency Shift** (both `p50` and `p99` increased `>= 50%`, pointing to shared infrastructure saturation such as CPU throttling, GC/memory limits, or shared DB connection pool contention across `k8s.pod.name` / `k8s.node.name` / `db.system`).
- [ ] **Step 2 — Compare Slow vs Baseline Cohorts**: Call `tempo_compare_span_cohorts` with `base_query='{ resource.service.name = "<service>" && kind = server }'` and `selection='{ duration > <tail_threshold> }'` matching the observed tail cutoff (e.g. `{ duration > 4s }` when investigating a `> 4s`–`5s` tail spike, passing `tenant` on multi-tenant backends) to isolate skewed attributes (`http.route`, `url.path`, `k8s.pod.name`, `k8s.node.name`, `service.version`, `flagd` variants). If the entry service delegates to a slow child service (e.g. `image-provider`), also run `tempo_compare_span_cohorts` on that child service if needed.
- [ ] **Step 3 — Sample Baseline and Slow Traces**:
  - Extract slow candidate traces via `tempo_get_exemplar_traces` (passing a valid TraceQL metrics query such as `'{ resource.service.name = "<service>" && kind = server && duration > 1500ms } | rate()'`, NOT PromQL) or `tempo_traceql_search` (`filters={"service": "<service>", "min_duration_ms": ...}`, `most_recent=True`).
  - Fetch a fast baseline trace (`filters={"service": "<service>", "max_duration_ms": ...}`, `most_recent=True`) when baseline vs regression trace IDs are not already provided.
- [ ] **Step 4 — Inspect Critical Path, Self-Time Hotspots & Time Gaps**:
  - Call `tempo_summarize_trace` on target trace IDs (or run `scripts/analyze_otlp_trace_critical_path.py --json '<otlp_json>'` / `--file <path>` when analyzing exported OTLP JSON payloads offline, merging overlapping parallel child intervals rather than naively summing child durations).
  - Apply [latency-heuristics.md](references/latency-heuristics.md): distinguish **Local Compute / GC Hotspot** (`self_time_ratio >= 0.40`) from **Downstream Wait** (entry span `duration_ms >= 80%` of trace with `self_time_ratio < 0.15` waiting on a slow leaf span).
  - **Uninstrumented Time-Gap Guardrail (`TRACE_TIME_GAPS`)**: When `has_time_gaps == True` (`critical_path_duration_ms < 0.5 * total_duration_ms` or large unaccounted parent-to-child gap), NEVER prematurely blame CPU saturation—call `tempo_get_diagnostics` to rule out `SPANS_DISCARDED` and check thread-pool queue wait, DNS/connection pool stalls, or disabled OTel instrumentation (`otel.enabled=false`).
- [ ] **Step 5 — Find Related & Async Consumer Traces**: Call `tempo_find_related_traces` (`correlation_strategy="span_links"`, `"temporal_neighbors"`, `"same_endpoint"`, `"downstream_cascade"`, or `"same_service_errors"`) to follow OTLP span links across async Kafka/messaging hops and check whether slowness is systemic, then run `tempo_summarize_trace` on linked consumer traces.
- [ ] **Step 6 — Diff Baseline vs Regression Traces**: Call `tempo_compare_traces(backend_id=..., trace_id_a=<baseline_trace_id>, trace_id_b=<comparison_trace_id>)`. Interpret `operation_diffs`, `only_in_comparison`, `duration_delta_ms`, `span_count_delta`, `error_count_delta`, and `attribute_diff` using [trace-diff-interpretation.md](references/trace-diff-interpretation.md) (**N+1 Fan-Out** `comparison_count / baseline_count >= 3` with `< 20%` per-call delta vs **Single-Operation Slowdown** `>= 60%` of `duration_delta_ms` vs **New Synchronous Dependency / Retry Amplification**).
- [ ] **Step 7 — Validate Bottleneck Classification**: `[GATE]` Confirm the exact bottleneck class before recommending flag rollbacks, batch RPC refactoring, async decoupling, or pod resource changes. Keep latency investigations bounded (`<= 12` MCP calls): once RED deltas, cohort skew, and 1–2 trace summaries/diffs establish the root cause, synthesize findings immediately rather than issuing unbounded cross-pillar queries.

## References & Offline Scripts

- Latency bottleneck heuristics (bimodal vs uniform, N+1, self-time vs downstream wait, time gaps): [latency-heuristics.md](references/latency-heuristics.md)
- Structural and duration trace diff interpretation: [trace-diff-interpretation.md](references/trace-diff-interpretation.md)
- Offline OTLP critical-path and merged-interval self-time analyzer: `scripts/analyze_otlp_trace_critical_path.py`
