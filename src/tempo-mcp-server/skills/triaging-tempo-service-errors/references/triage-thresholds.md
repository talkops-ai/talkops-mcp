# Service Error Triage Thresholds & Heuristics

Use these thresholds to interpret raw facts returned by `tempo_analyze_service_red`, `tempo_compare_span_cohorts`, and `tempo_summarize_trace`.

## 1. RED Error Ratio Severity Matrix

| Severity | `error_ratio` Threshold | Additional Signal Conditions | Operational Classification |
| :--- | :--- | :--- | :--- |
| `CRITICAL` | `>= 0.05` (5.0%) | Sustained for `>= 5m` OR `error_rate_per_sec >= 1.0` | Active service outage or severe regression requiring immediate rollback or traffic drain. |
| `WARNING` | `0.01 <= error_ratio < 0.05` (1%–5%) | Localized to specific route/pod in `tempo_compare_span_cohorts` | Partial degradation, canary failure, or single-instance fault. |
| `ELEVATED` | `0.001 <= error_ratio < 0.01` (0.1%–1%) | Above baseline but within SLO burn budget | Transient downstream errors or retryable timeouts. |
| `NOMINAL` | `< 0.001` (< 0.1%) | Zero `SPAN_ERRORS_PRESENT` on critical path | Healthy operation. |

## 2. Cohort Skew Interpretation (`tempo_compare_span_cohorts`)

When `tempo_compare_span_cohorts` (`compare({base_query}, status = error)`) returns attribute distributions:
- **Single-Pod Skew**: If a single `k8s.pod.name` or `service.instance.id` accounts for `>= 60%` of error cohort spans while representing `< 20%` of baseline spans, classify as an infrastructure/node/pod defect rather than a code bug.
- **Version/Canary Skew**: If a specific `service.version` or `deployment.environment` accounts for `>= 80%` of error cohort spans, classify as a bad deployment rollout.
- **Endpoint Skew**: If a single `http.route` or `rpc.method` accounts for `>= 75%` of error cohort spans, narrow subsequent `tempo_traceql_search` calls to that route.

## 3. Observation Code Interpretation in Trace Summaries

- `SPAN_ERRORS_PRESENT`: Compare `deepest_error_span.service_name` (`error_origin_service`) with the root span `root_service`. The deepest span in the call tree (`max(depth)`) with `status == "error"` is the primary fault origin candidate unless an earlier sibling span failed chronologically first (`start_time_unix_nano`).
- `TRACE_TIME_GAPS`: Indicates uninstrumented internal work, thread-pool starvation, GC pause, or dropped child spans from an async queue or rate-limited OTel collector.
