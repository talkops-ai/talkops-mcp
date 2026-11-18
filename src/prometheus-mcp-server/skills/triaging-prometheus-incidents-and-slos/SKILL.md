---
name: triaging-prometheus-incidents-and-slos
description: Triages Kubernetes service incidents, latency regressions, USE saturation, firing Prometheus alerts, and Google SRE multi-window SLO error-budget burn rates using RED golden signals, period comparisons, and OpenMetrics trace exemplars. Use when investigating an outage or page, evaluating 30-day SLO error-budget burn and hours to exhaustion, generating multi-window SLO burn-rate rules, diagnosing RPS drops vs target-down blind spots, or pivoting from latency/error spikes via exemplars. Do not use for clustering Alertmanager alert storms or creating Alertmanager silences (use triaging-alertmanager-alerts or managing-alert-silences), LogQL log summarization (use triaging-loki-incidents-and-errors), or TraceQL span-cohort diffs (use triaging-tempo-service-errors).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: prometheus
---

# Triaging Prometheus Incidents and SLOs

Executes a structured, low-turn SRE incident triage and Google SRE multi-window SLO burn-rate workflow across single and multi-backend Prometheus environments. Never shell out to `kubectl` or raw `curl` when MCP resources and tools are available. **Slash-Command Entrypoint**: Whenever the user request starts with `/triage`, you MUST immediately read `commands/triage.md` in the workspace root (`read_file`) before running tool calls so you follow the plugin's correlated 4-signal triage structure.

## MCP Execution Primitives Used

- **Resources**:
  - `prom://system/backends` and `prom://system/backends/{backend_id}` — discover registered Prometheus/Thanos/Mimir backends (`default`, regional clusters like `otel-demo-eu`, etc.) and verify runtime health/version before querying.
  - `prom://topology/targets` — verify target scrape health (`up` vs `down`).
  - `prom://rules/groups` — inspect active SLO recording and alerting rule groups.
- **Tools (`diagnostics`, `query`, `rules` toolsets)**:
  - `prom_get_diagnostics` — **Step 0 check**: verify backend health and `TARGETS_DOWN` observations (`include="targets"` or `"overview"`) before trusting `0` RPS / `0%` error graphs.
  - `prom_get_firing_alerts` — inspect active `firing` vs `pending` Prometheus alert evaluations.
  - `prom_analyze_service_red` — compute Rate (RPS), Error Ratio (%), p50/p95/p99 Duration, `HIGH_TAIL_LATENCY_SKEW` (`p99/p50 >= 5.0`), and exemplars across `auto`, `prometheus_http`, `prometheus_native`, `otel`, `otel_utf8`, `spanmetrics`, and `otel_rpc` conventions.
  - `prom_evaluate_slo_burn` — compute Google SRE multi-window multi-burn-rate consumption (`14.4x` `1h/5m` `PAGE_CRITICAL_FAST_BURN`, `6.0x` `6h/30m` `PAGE_HIGH_BURN`, `3.0x` `24h/2h`, `1.0x` `72h/6h` `TICKET_SLOW_BURN` / `WITHIN_ERROR_BUDGET`) and `estimated_exhaustion_hours`.
  - `prom_compare_periods` — compare current incident metrics against historical baselines (`baseline_offset="1h"` or `"24h"`), flagging `SIGNIFICANT_SPIKE` or `SIGNIFICANT_DROP`.
  - `prom_query_exemplars` — extract W3C `trace_id` / `span_id` exemplars from latency buckets or error counters to pivot into Tempo.
  - `prom_query_instant` / `prom_query_range` — evaluate USE infrastructure/container saturation (CPU CFS throttling, memory limits/`OOMKilled`, JVM GC).

## Step-by-Step Triage Workflow

### 1. Discover Backend & Verify Scraper Health First `[HIGH FREEDOM]`
1. Read `prom://system/backends` and `prom://system/backends/{backend_id}` (especially in multi-cluster/regional setups, passing explicit `backend_id` to every subsequent `prom_*` tool call).
2. **Always** call `prom_get_diagnostics(backend_id=..., include="targets")` (and check `prom://topology/targets`) + `prom_get_firing_alerts(backend_id=..., state="firing")` **before** interpreting missing traffic or `0%` error rates!
   - **Blind-Spot vs. Upstream Drop**:
     - If `TARGETS_DOWN` (`up == 0`) affects the target service, `0` RPS / `0%` error is a **telemetry blind spot** from broken scraping — hand off to `configuring-prometheus-scraping-and-discovery`.
     - If scrape targets are `UP` (`up == 1`), local error ratio is near `0%`, and local latency is healthy, yet RPS on the queried service/funnel (e.g. `cart-checkout-funnel`) plunged $\ge 50\%$ (`SIGNIFICANT_DROP` in `prom_compare_periods`), diagnose an **upstream traffic blockage/drop** (gateway/Envoy `frontend-proxy`, `frontend`, or Traefik ingress routing/funnel failure) rather than blaming unrelated downstream alerts!

### 2. Evaluate RED Signals, USE Saturation & Multi-Window SLO Burn `[HIGH FREEDOM]`
Consult [references/red-use-golden-signals.md](references/red-use-golden-signals.md) and [references/slo-multiwindow-burn-rates.md](references/slo-multiwindow-burn-rates.md):
1. Call `prom_analyze_service_red(backend_id=..., service_selector=..., lookback="15m", metric_convention=..., include_exemplars=True)` (pass `metric_convention="otel"` when querying OpenTelemetry `http_server_request_duration_seconds_*` metrics; if `p99 / p50 >= 5.0`, flag `HIGH_TAIL_LATENCY_SKEW`).
2. For container/JVM saturation (high latency with `0%` 5xx or pod restarts), evaluate all 3 **USE** dimensions via `prom_query_instant` / `prom_query_range` (**always pass `detail="summary"`** to protect context budget!) and `prom_compare_periods` (`baseline_offset="1h"` or `"24h"`), and **explicitly report the baseline vs. current saturation shift (%)** in your response:
   - **Utilization**: CPU usage vs limit, memory working set vs limit.
   - **Saturation**: Container CPU CFS throttling ratio (`rate(container_cpu_cfs_throttled_periods_total[5m]) / rate(container_cpu_cfs_periods_total[5m])`) and JVM GC pause duration (`rate(jvm_gc_duration_seconds_sum[5m])`).
   - **Errors**: `kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}` and container restart counts.
3. Call `prom_evaluate_slo_burn(backend_id=..., error_query=..., total_query=..., slo_target=..., window_days=30)`:
   - Error budget $E = 1 - \text{SLO}$, burn rate $B = \frac{\text{error\_ratio}}{E}$, hours to exhaustion $= \frac{720}{B}$ (for 30d).
   - Distinguish **3 AM paging** (`PAGE_CRITICAL_FAST_BURN` $\ge 14.4\times$ over `1h/5m`; `PAGE_HIGH_BURN` $\ge 6.0\times$ over `6h/30m`) from **daytime ticket** (`TICKET_SLOW_BURN` $1.0\times\text{–}3.0\times$ over `72h/6h` or `24h/2h` — never wake on-call at 3 AM for a `~1.1x` slow burn; instead confirm **no 3 AM page** and run/recommend daytime trend comparison via `prom_compare_periods`!).

### 3. Pivot Across Pillars Cleanly `[MEDIUM FREEDOM]`
Read [references/cross-pillar-handoffs.md](references/cross-pillar-handoffs.md) and **read [references/incident-triage-template.md](references/incident-triage-template.md)** when formatting `/triage` or full incident reports:
- **Exemplars $\rightarrow$ Tempo**: Extract `trace_ids` via `prom_query_exemplars` and invoke `tempo` MCP (`tempo_summarize_trace` / `tempo_get_trace`) rather than guessing span root causes inside Prometheus.
- **Missed Pages / Silences $\rightarrow$ Alertmanager**: Confirm `state == "firing"` in `prom_get_firing_alerts` + `prom_get_diagnostics`, **explicitly explain the Prometheus vs. Alertmanager bounded context** (Prometheus evaluates alerting rule expressions from `pending` $\rightarrow$ `firing`, whereas Alertmanager owns routing trees, **inhibitions**, silences, `mute_time_intervals`, and receiver notification delivery), and pivot to `alertmanager` MCP (`am_explain_routing`, `am_check_notification_health`, `am_preview_silence`).

### 4. Generate Multi-Window Multi-Burn-Rate SLO Rules `[MEDIUM FREEDOM]`
To generate production Google SRE multi-window SLO recording (`5m, 30m, 1h, 2h, 6h, 24h, 72h` with `clamp_min(..., 1e-9)`) and alerting (`14.4x`, `6.0x`, `3.0x`, `1.0x`) rules, run [scripts/generate_slo_rules.py](scripts/generate_slo_rules.py):
- Validate that `slo_target` is a decimal ratio strictly in `(0.5, 1.0)` (normalize percentage inputs like `99.9%` $\rightarrow$ `0.999`, and explain why `1.0` / `100%` has zero error budget $1 - 1.0 = 0$ causing division-by-zero burn rates!):
  ```bash
  python3 .agents/skills/triaging-prometheus-incidents-and-slos/scripts/generate_slo_rules.py \
    --service payment --slo-target 0.9995 \
    --error-metric 'rpc_server_errors_total{service_name="payment",service_namespace="otel-demo"}' \
    --total-metric 'rpc_server_requests_total{service_name="payment",service_namespace="otel-demo"}'
  ```
  *(If running outside `.agents/skills`, invoke `./scripts/generate_slo_rules.py` relative to this skill directory.)*

## Reference Documentation

- [RED and USE Golden Signals Reference](references/red-use-golden-signals.md)
- [Google SRE Multi-Window Multi-Burn-Rate Reference](references/slo-multiwindow-burn-rates.md)
- [Cross-Pillar Handoffs: Alertmanager, Tempo, and OpenTelemetry](references/cross-pillar-handoffs.md)
- [Incident & SLO Triage Report Template](references/incident-triage-template.md)
