# Cross-Pillar Handoffs: Alertmanager, Tempo, and OpenTelemetry

## Bounded Context Rules

`prometheus-mcp-server` owns **metric collection, TSDB storage, PromQL evaluation, exemplars, and rule firing state** (`/api/v1/rules`, `/api/v1/alerts`). Never attempt to manage Alertmanager silences or query TraceQL spans directly inside `prometheus-mcp-server`.

## 1. Handoff to `alertmanager-mcp-server` (`am_*`)

When `prom_get_firing_alerts` shows an alert in `firing` state, hand off to `alertmanager-mcp-server` for notification lifecycle operations:

- **"Why didn't this firing Prometheus alert page on-call?"**
  - Invoke `am_explain_routing(backend_id=..., labels=..., check_live_state=True)` or `am_check_notification_health` (skill: `diagnosing-missed-notifications`).
- **"Silence this noisy alert during maintenance / mitigation"**
  - Invoke `am_preview_silence` followed by `am_silence_alert` or `am_create_silence` (skill: `managing-alert-silences`).
- **"Group firing alerts into incident clusters across receivers"**
  - Invoke `am_summarize_oncall` or `am_list_alert_groups` (skill: `triaging-alertmanager-alerts`).

## 2. Handoff to `tempo-mcp-server` (`tempo_*`)

When `prom_analyze_service_red` or `prom_query_exemplars` returns OpenTelemetry `trace_ids`:

- **"Inspect the exact slow or failing request trace"**
  - Pass each `trace_id` from `prom_query_exemplars` to `tempo_get_trace(trace_id=...)` or `tempo_summarize_trace(trace_id=...)` in `tempo-mcp-server` (skill: `triaging-tempo-service-errors`).
- **"Compare trace span durations before vs. after deploy"**
  - Pivot to `tempo-mcp-server` skill `investigating-tempo-latency-regressions` (`tempo_compare_traces`).

## 3. Handoff to `opentelemetry-mcp-server`

- When a service lacks Prometheus histograms or exemplar labels (`traceID`), hand off to `opentelemetry-mcp-server` to configure the OpenTelemetry Collector `prometheusremotewrite` or `spanmetrics` connector.
