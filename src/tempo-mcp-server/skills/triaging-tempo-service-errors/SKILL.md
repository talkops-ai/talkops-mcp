---
name: triaging-tempo-service-errors
description: Triages distributed service errors and incidents in Grafana Tempo by computing RED severity, comparing error vs baseline span cohorts (canary version, single-pod, or route skew), pivoting from metrics exemplars or W3C traceparent/JSON/logfmt logs, and isolating deepest error origin spans. Use when investigating 5xx spikes, elevated RPC error rates, failing requests across microservices, or running `/triage`. Do not use for pure zero-error latency regressions (use investigating-tempo-latency-regressions), Loki-only log signature summaries (use triaging-loki-incidents-and-errors), Prometheus multi-burn SLO math (use triaging-prometheus-incidents-and-slos), or Tempo cluster/ring failures (use diagnosing-tempo-ingestion-and-health).
---

# Triaging Tempo Service Errors

## Preconditions

- Read `tempo://server/capabilities` and `tempo://system/backends` (and `commands/triage.md` when invoked via `/triage`) via MCP resources before issuing queries.
- Confirm the target `backend_id`, target service name, tenant (`X-Scope-OrgID`), and time window (`since`).
- Never guess span or resource attribute names; verify with `tempo_get_attribute_names` and `tempo_get_attribute_values`.

## Triage Workflow Checklist

- [ ] **Step 1 — Verify Capabilities & Schema**: Read `tempo://server/capabilities` and `tempo://system/backends`, then call `tempo_get_attribute_names` (`scope="resource"` and `scope="span"`) to confirm `resource.service.name` and attribute keys.
- [ ] **Step 2 — Establish Entry Point**:
  - If starting from high-error/latency metrics or alerts, call `tempo_get_exemplar_traces` with a valid TraceQL metrics expression (for example `'{ resource.service.name = "<service>" && status = error } | rate()'`, NOT PromQL) to extract `trace_candidates`.
  - If starting from raw container error logs or a multi-line log bundle (`traceparent`, `otelTraceID`, `traceId`, `trace_id`), run `scripts/extract_trace_ids_from_logs.py --text '<logs>'` to filter out invalid all-zero (`00000000000000000000000000000000`) trace IDs and call `tempo_get_trace_from_log` on valid log lines.
  - If starting from a service name, call `tempo_analyze_service_red` (`service`, `since`, `baseline_offset`) to measure `rate_rps`, `error_rate_rps`, `error_ratio`, and p50/p95/p99 durations.
- [ ] **Step 3 — Evaluate Triage Thresholds**: Apply the deterministic severity matrix in [triage-thresholds.md](references/triage-thresholds.md) (`CRITICAL` if `error_ratio >= 0.05` OR `error_rate_per_sec >= 1.0`; `WARNING` if `0.01 <= error_ratio < 0.05`; `ELEVATED` if `0.001 <= error_ratio < 0.01`; `NOMINAL` if `< 0.001`) and run `scripts/render_incident_report.py` to compute exact report JSON fields.
- [ ] **Step 4 — Isolate Error Cohort Drivers**: Call `tempo_compare_span_cohorts` with `base_query='{ resource.service.name = "<service>" }'` and `selection='{ status = error }'` to check canary version skew (`>= 80%` on one `service.version`), single-pod defect skew (`>= 60%` error share vs `< 20%` baseline share on one `k8s.pod.name`), or route skew (`>= 75%` on one `http.route` / `rpc.method`).
- [ ] **Step 5 — Sample Recent Failing Traces**: Call `tempo_traceql_search` with `filters={"service": "<service>", "status": "error"}` (or narrow TraceQL `query`) and `most_recent=True`.
- [ ] **Step 6 — Inspect Deepest Error Origin & Trace Resource**: Read `tempo://traces/{backend_id}/{trace_id}` via MCP resources and call `tempo_summarize_trace` (plus `tempo_get_trace` when inspecting `exception.type`, `exception.message`, `exception.stacktrace`, or pod attributes). Compare `root_service` against `error_origin_service` (`deepest_error_span` at `max(depth)`) so upstream cascading 502/503 gateways are exonerated when a downstream service failed.
- [ ] **Step 7 — Pivot Across Signals**: Follow [cross-pillar-handoffs.md](references/cross-pillar-handoffs.md) to correlate `error_origin_service`, `k8s.pod.name`, and `trace_id` with Grafana Loki (`loki_correlate_trace_logs`), Prometheus, or Alertmanager.
- [ ] **Step 8 — Render Incident Brief**: `[GATE]` Run `scripts/render_incident_report.py` and format the final incident brief via [incident-brief-template.md](references/incident-brief-template.md), citing `tempo://traces/<backend_id>/<trace_id>`.

## Decision Rules

1. **Downstream vs Local Origin**:
   - When `error_origin_service` differs from the entry `root_service` and `deepest_error_span` has `status = "error"`, exonerate the upstream gateway/caller as a cascading victim and direct remediation (or rollback) to `error_origin_service`.
   - When `deepest_error_span` lacks `exception` events on the trace span, call `tempo_get_trace` for exact pod/timestamp metadata and pivot to Loki (`loki_correlate_trace_logs`) scoped to `error_origin_service`.
2. **TraceQL Metrics (`local-blocks`) Disabled Fallback**:
   - If `tempo_analyze_service_red` or `tempo_compare_span_cohorts` fails (or `tempo://server/capabilities` / `tempo_get_diagnostics` shows `local-blocks` absent), pivot cleanly to `tempo_get_attribute_names` -> `tempo_traceql_search` (`status = error`, `limit=20`) -> `tempo_summarize_trace` -> `tempo_get_trace` across multiple sampled failing traces to determine `error_origin_service` and common failing pod/version/route attributes.

## References & Offline Scripts

- Thresholds and severity classification: [triage-thresholds.md](references/triage-thresholds.md)
- Cross-pillar correlation playbooks (Prometheus, Loki, Kubernetes): [cross-pillar-handoffs.md](references/cross-pillar-handoffs.md)
- Structured incident report format: [incident-brief-template.md](references/incident-brief-template.md)
- Offline log trace-ID extractor: `scripts/extract_trace_ids_from_logs.py`
- Offline incident report renderer: `scripts/render_incident_report.py`
