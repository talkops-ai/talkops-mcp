# Incident Brief Template

Format service error triage findings using the structure below:

```markdown
## Tempo Service Error Triage Brief: <service_name>

- **Backend**: `<backend_id>`
- **Window**: `<start>` to `<end>`
- **Severity**: `<CRITICAL | WARNING | ELEVATED | NOMINAL>`

### 1. RED Metrics Summary (`tempo_analyze_service_red`)
- **Request Rate**: `<request_rate_per_sec>` req/s
- **Error Rate**: `<error_rate_per_sec>` err/s (`<error_ratio * 100>`%)
- **Latency Quantiles**: p50=`<p50>`s | p90=`<p90>`s | p95=`<p95>`s | p99=`<p99>`s

### 2. Error Cohort Skew (`tempo_compare_span_cohorts`)
- **Base Query**: `<base_query>`
- **Selection**: `<selection>`
- **Top Correlated Attributes**: `<attribute key=value deltas>`

### 3. Representative Failing Traces (`tempo_summarize_trace`)
- **Trace ID**: `<trace_id>` (`tempo://traces/<backend_id>/<trace_id>`)
- **Entry Root Service / Operation**: `<root_service>` / `<root_operation>` (`<duration_ms>` ms)
- **Error Origin Service**: `<error_origin_service>`
- **Deepest Error Span**: `<deepest_error_span.name>` (span_id=`<deepest_error_span.span_id>`, depth=`<deepest_error_span.depth>`, duration=`<deepest_error_span.duration_ms>` ms)
- **Observation Codes**: `<observation_codes>`

### 4. Recommended Next Actions
1. `<Action 1 grounded in error_origin_service and cohort skew>`
2. `<Action 2 grounded in cross-pillar logs or rollout rollback>`
```
