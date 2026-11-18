---
name: triaging-loki-incidents-and-errors
description: Triages production incidents, 5xx spikes, CrashLoopBackOff/OOM pods, silent log streams, canary regressions, latency-without-5xx slowdowns, and cross-service failures using Loki N-to-1 summaries, period/cohort comparisons, error signature clustering, and trace/order ID log correlation. Use when investigating outages in Loki, comparing current vs baseline or canary vs stable logs, correlating trace_id or order_id timelines across services, clustering raw error lines, or running /triage. Do not use for Tempo span-waterfall analysis (use triaging-tempo-service-errors), Prometheus SLO burn math (use triaging-prometheus-incidents-and-slos), Alertmanager alert-storm grouping (use triaging-alertmanager-alerts), or LogQL syntax tutorials (use authoring-logql-and-analyzing-logs).
license: Apache-2.0
metadata:
  author: TalkOps
  version: "0.2.0"
  domain: observability
  service: grafana-loki
---

# Triaging Loki Incidents and Errors

Use this skill to execute a fast, token-efficient Grafana Loki 3.x incident triage workflow that isolates root-cause error signatures, separates new deployment regressions from background noise, and reconstructs chronological cross-service failure timelines.

## Core Rule: Aggregate ($N \to 1$) First, Drill Down Second

Never begin an outage investigation by dumping hundreds of raw `loki_query_range` lines. Start with $N \to 1$ analysis tools (`loki_summarize_service_logs`, `loki_compare_periods`, `loki_correlate_trace_logs`) and consult [references/incident-triage-sop.md](references/incident-triage-sop.md), [references/cross-pillar-correlation-guide.md](references/cross-pillar-correlation-guide.md), and [references/incident-brief-template.md](references/incident-brief-template.md).

## Step-by-Step Incident Triage Workflow

### Step 1: Verify Loki Readiness & Backend Context
1. Read `loki://system/health` and `loki://config/backends` first (and `commands/triage.md` when invoked via `/triage`).
2. Confirm the target workload selector (`{service_name="<service>", namespace="<namespace>"}`) and pass `org_id` whenever a tenant is specified.

### Step 2: One-Shot Service Log Digest (`loki_summarize_service_logs`)
- Call `loki_summarize_service_logs(selector=..., start="now-15m", org_id=...)` to inspect `index_stats`, `estimated_error_ratio`, `top_error_signatures`, and `extracted_trace_ids`.

### Step 3: Isolate New Regressions & Canary Skew (`loki_compare_periods`)
- **Time-over-Time**: Call `loki_compare_periods(selector=..., start="now-15m", baseline_offset="1h", org_id=...)` and prioritize `new_error_signatures` (`0` occurrences in baseline).
- **Canary vs. Stable Cohorts**: Call `loki_compare_periods(selector='{service_name="<service>", namespace="<namespace>", version="<canary>"}', baseline_selector='{service_name="<service>", namespace="<namespace>", version="<stable>"}', start="now-20m", end="now")` over the identical window to decide between promotion vs. rollback.

### Step 4: Normalize & Cluster Raw Error Lines Locally (`extract_error_signatures.py`)
Whenever given raw error lines or sampled error logs, run [scripts/extract_error_signatures.py](scripts/extract_error_signatures.py) to normalize timestamps, IPs, UUIDs, 32-hex trace IDs, and retry integers into canonical signatures while extracting `trace_ids` and `session_ids`:
```bash
python3 .agents/skills/triaging-loki-incidents-and-errors/scripts/extract_error_signatures.py \
  --input error_lines.txt --json
```

### Step 5: Cross-Service Chronological Root Cause (`loki_correlate_trace_logs`)
1. Read [references/cross-pillar-correlation-guide.md](references/cross-pillar-correlation-guide.md) when correlating `trace_id` / `order_id` across services, pivoting between Loki/Prometheus/Tempo, or handling unpropagated trace fallbacks.
2. Call `loki_correlate_trace_logs(correlation_id="...", scope_selector='{namespace="<namespace>"}', correlation_key="trace_id", org_id=...)` (or pass `correlation_key="order_id"` / `"request_id"` when OTel tracing is disabled!).
3. **Earliest-Chronological-Error Rule**: Order events by timestamp—the **earliest service** logging `FATAL`/`ERROR`/exhaustion (e.g., database connection exhaustion or downstream RPC `Unavailable`) is the true root cause; upstream services logging `502`/`503`/`Unavailable` milliseconds later are cascading victims.
4. **Unpropagated Trace Timestamp Fallback**: If an un-instrumented/legacy service is missing from `loki_correlate_trace_logs`, run a tightly bounded `±5s` `loki_query_range` (`start="<span_ts - 5s>"`, `end="<span_ts + 5s>"`, `max_log_lines=50`) scoped strictly to `{service_name="<legacy-service>", namespace="<namespace>"}`.

### Step 6: Specialized Incident SOPs ([references/incident-triage-sop.md](references/incident-triage-sop.md))
- **CrashLoopBackOff / OOMKilled**: Run `loki_summarize_service_logs`, `loki_compare_periods`, `loki_query_range(..., direction="backward", max_log_lines=50)` for the final OOM/panic death rattle, and `loki_query_range(..., direction="forward", max_log_lines=50)` for initial 5-second startup config/port/dependency errors.
- **Latency Degradation Without 5xx**: Summarize affected services, query slow/warning signals (`duration_ms > 1000`, queue/consumer lag, GC pauses, `retrying`, `deadline exceeded`), compute `quantile_over_time(0.95, ... | unwrap duration_ms | __error__="" [5m]) by (route)` via `loki_query_instant` / `loki_query_range`, and pivot slow `trace_id`s via `loki_correlate_trace_logs` + Tempo.
- **Silent Service / Missing Logs**: Call `loki_get_series(..., start="now-2h")` to check last-seen stream activity AND `loki_get_diagnostics(include_metrics=True)` to distinguish Loki `per_stream_rate_limit`/`rate_limited`/`line_too_long` drops from crashed pods or `otel.enabled=false` Helm resets.
- **Interactive Incident Commander View**: After summarizing via `loki_summarize_service_logs`, call `loki_query_a2ui(..., max_log_lines=100)` and format conclusions using [references/incident-brief-template.md](references/incident-brief-template.md).

## Key Reference Guides & Scripts

- [references/incident-triage-sop.md](references/incident-triage-sop.md) — Playbooks for 5xx spikes, latency-without-5xx, CrashLoopBackOff/OOMs, and silent services.
- [references/cross-pillar-correlation-guide.md](references/cross-pillar-correlation-guide.md) — Pivoting across Loki logs, Prometheus metrics/exemplars, and Tempo traces (`±5s` fallback).
- [references/incident-brief-template.md](references/incident-brief-template.md) — 5-section executive & engineering Incident Brief format.
- [scripts/extract_error_signatures.py](scripts/extract_error_signatures.py) — Deterministic log signature normalizer and `trace_id`/`session_id` extractor.
