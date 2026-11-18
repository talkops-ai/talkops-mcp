# Loki Incident Triage Standard Operating Procedure (SOP)

## Table of Contents
1. [Playbook 1: Sudden HTTP 5xx or Error Spike](#1-playbook-1-sudden-http-5xx-or-error-spike)
2. [Playbook 2: Latency Degradation Without Obvious 5xx Spike](#2-playbook-2-latency-degradation-without-obvious-5xx-spike)
3. [Playbook 3: Kubernetes Pod CrashLoopBackOff or OOMKilled](#3-playbook-3-kubernetes-pod-crashloopbackoff-or-oomkilled)
4. [Playbook 4: Silent Service / Missing Logs](#4-playbook-4-silent-service--missing-logs)

---

## 1. Playbook 1: Sudden HTTP 5xx or Error Spike

1. **Quantify the Blast Radius**:
   - Call `loki_summarize_service_logs(selector='{service_name="<svc>", namespace="<ns>"}', start="now-30m")`.
   - Record `estimated_error_ratio` and top 5 error templates.
2. **Isolate Newly Introduced Signatures**:
   - Call `loki_compare_periods(selector='{service_name="<svc>", namespace="<ns>"}', start="now-15m", baseline_offset="1h")`.
   - If `new_error_signatures` is non-empty, inspect the top new signature first—it pinpoints the regression introduced during the last 1h.
3. **Trace Downstream Dependencies**:
   - Extract a `trace_id` from `extracted_trace_ids` and run `loki_correlate_trace_logs(correlation_id="<id>")`.
   - Identify whether the error originated inside `<svc>` (e.g., `NullPointerException`, schema migration error) or an upstream/downstream dependency (`connection refused`, `deadline exceeded`).

---

## 2. Playbook 2: Latency Degradation Without Obvious 5xx Spike

1. **Check Slow Request Logs**:
   - Query logs with `loki_query_range` using a numeric duration filter:
     ```logql
     {service_name="<svc>", namespace="<ns>"} |= "duration" | json duration_ms="duration_ms" | duration_ms > 1000 | __error__=""
     ```
2. **Check Resource Exhaustion Signals**:
   - Search for retry storms, connection pool starvation, or lock contention:
     ```logql
     {service_name="<svc>", namespace="<ns>"} |~ "(?i)(pool exhausted|timeout|retrying|backoff|deadlock|too many connections)"
     ```
3. **Compare Latency Quantiles**:
   - Use `loki_query_instant` with `quantile_over_time(0.95, ... | unwrap duration_ms | __error__="" [5m]) by (route)` to identify which endpoint regressed.

---

## 3. Playbook 3: Kubernetes Pod CrashLoopBackOff or OOMKilled

1. **Inspect Last Lines Before Termination**:
   - Query the crashing workload with `direction="backward"` and a narrow window around the restart:
     ```logql
     {namespace="<ns>", service_name="<svc>"} |~ "(?i)(panic|fatal|oom|out of memory|sigterm|sigkill|segfault|unhandled)"
     ```
2. **Check Startup / Configuration Errors**:
   - Often a CrashLoopBackOff is caused by a missing secret, failed DB migration, or port binding conflict logged within the first 5 seconds of container startup.

---

## 4. Playbook 4: Silent Service / Missing Logs

1. **Verify Stream Existence**:
   - Call `loki_get_series` or `loki_summarize_service_logs` to see if active streams exist.
2. **Check Loki Ingestion Drops**:
   - If logs disappeared abruptly, check whether Loki is rejecting or rate-limiting the stream via `loki_get_diagnostics` (look for `per_stream_rate_limit` or `max_line_size_exceeded`).
