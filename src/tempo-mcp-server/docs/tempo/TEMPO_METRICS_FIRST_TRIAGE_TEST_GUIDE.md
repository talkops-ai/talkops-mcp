# Metrics-First Triage (RED) Test Guide — Tempo MCP Server (OTel Demo)

**Phase 5 of 7** in the Tempo end-to-end journey.
**Previous phase**: [TraceQL Query Builder](TEMPO_TRACEQL_BUILDER_TEST_GUIDE.md)
**Next phase**: [Schema Exploration](TEMPO_SCHEMA_EXPLORATION_TEST_GUIDE.md)

> This phase performs a full RED (Rate, Errors, Duration) analysis for the `checkout`
> service — measuring aggregate metrics via TraceQL, then pivoting from metrics to
> concrete exemplar traces, and from log lines to traces. Demonstrates both cross-pillar
> pivot tools.
>
> **Target service**: `checkout` — Go service orchestrating payment, shipping, cart.

---

## Prerequisites (Completed in Phase 4)

| Component | Status |
|-----------|--------|
| ✅ TraceQL query construction | `tempo_traceql_search` — working with raw and K8s-friendly filters |
| ✅ Attribute discovery | `tempo_get_attribute_names`, `tempo_get_attribute_values` — known |
| ✅ Metrics-generator working | `tempo_traceql_metrics_range` — time series returned in Phase 1 |
| ✅ Query policies understood | `tempo_get_query_policies` — limits known |

---

## The Starting Point

Phase 4 built TraceQL queries. Now you want to analyze the overall health of a service using the RED methodology — the standard approach for service-level monitoring:

- **R**ate — How many requests per second?
- **E**rrors — What fraction are failing?
- **D**uration — How long do requests take? (P50, P95, P99)

After measuring RED metrics, you'll pivot from aggregate metrics to specific traces using exemplar IDs, and parse trace IDs from log lines for cross-pillar correlation.

---

## Phase 1: Rate

### Step 1.1: Overall Request Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What's the request rate for "checkout" over the last 3 hours?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" } | rate()", "since": "3h"}` |
| **Internal action** | Validates TraceQL. Resolves time range. Calls `GET /api/metrics/query_range`. Returns matrix time series with spans/second. |
| **Expected output** | `{"effective_query": "{ resource.service.name = \"checkout\" } | rate()", "result_type": "matrix", "series": [{"labels": {}, "points": [{"ts": <epoch>, "value": "0.35"}, ...]}]}` |

**What to check:**

| Metric | What to Verify |
|--------|----------------|
| `result_type` | `"matrix"` — time series |
| `points` values | Steady baseline or trending? Sudden drops = possible outage |
| Rate magnitude | Typical for the service? (checkout may be lower than frontend) |

### Step 1.2: Rate by Service (Cluster-Wide)

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the request rate per service across the whole cluster.` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ } | rate() | by(resource.service.name)", "since": "1h"}` |
| **Internal action** | Groups by service name. Returns one series per service. |

---

## Phase 2: Errors

### Step 2.1: Error Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What's the error rate for "checkout" over the last 3 hours?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" && status = error } | rate()", "since": "3h"}` |

### Step 2.2: Error Rate by Service

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the error rate by service across all services.` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ status = error } | rate() | by(resource.service.name)", "since": "1h"}` |

### Step 2.3: Error Count

| Field | Value |
|-------|-------|
| **Prompt** | `How many error traces from "checkout" in the last hour?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" && status = error } | count_over_time()", "since": "1h"}` |

---

## Phase 3: Duration

### Step 3.1: P99 Latency

| Field | Value |
|-------|-------|
| **Prompt** | `What's the P99 latency for "checkout" over the last 3 hours?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" } | quantile_over_time(duration, 0.99)", "since": "3h"}` |

### Step 3.2: P50 Latency (Median)

| Field | Value |
|-------|-------|
| **Prompt** | `What's the median latency for "checkout"?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" } | quantile_over_time(duration, 0.5)", "since": "3h"}` |

### Step 3.3: Duration Histogram

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the latency distribution for "checkout".` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" } | histogram_over_time(duration)", "since": "1h"}` |

### Step 3.4: Average Duration

| Field | Value |
|-------|-------|
| **Prompt** | `What's the average span duration for "checkout"?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" } | avg_over_time(duration)", "since": "1h"}` |

---

## Phase 4: Instant Metrics (Current Snapshot)

### Step 4.1: Current Error Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What's the current error rate for "checkout" right now?` |
| **Tool** | `tempo_traceql_metrics_instant` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" && status = error } | rate()", "since": "1h"}` |
| **Internal action** | Calls `GET /api/metrics/query` (instant query endpoint). Returns a single point-in-time value (vector). |
| **Expected output** | `{"effective_query": "...", "result_type": "vector", "series": [{"labels": {}, "value": "0.02"}]}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `result_type` | `"vector"` — instant (not time series) |
| `value` | Current error rate as a single number |

### Instant vs Range

| Feature | `tempo_traceql_metrics_instant` | `tempo_traceql_metrics_range` |
|---------|-------------------------------|------------------------------|
| Returns | Single value (vector) | Time series (matrix) |
| Use case | Current snapshot | Trend analysis |
| API endpoint | `/api/metrics/query` | `/api/metrics/query_range` |

---

## Phase 5: Cross-Pillar Pivot — Metrics to Traces

### Step 5.1: Get Exemplar Traces from Error Rate Metric

| Field | Value |
|-------|-------|
| **Prompt** | `Get exemplar trace IDs from the error rate metrics for "checkout".` |
| **Tool** | `tempo_get_exemplar_traces` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" && status = error } | rate()", "since": "1h"}` |
| **Internal action** | (1) Runs the metrics query. (2) Extracts exemplar trace IDs from the metric series. (3) Returns a list of concrete trace IDs that contributed to the metric value. |
| **Expected output** | `{"query": "...", "exemplar_trace_ids": ["abc123...", "def456..."], "total_exemplars": N, "note": "Use tempo_summarize_trace to analyze these traces."}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `exemplar_trace_ids` | Concrete trace IDs extracted from the metric |
| `total_exemplars` | How many exemplars were found |
| If empty | Exemplars may not be supported or no matching spans in the window |

### Step 5.2: Deep Dive into an Exemplar

| Field | Value |
|-------|-------|
| **Prompt** | `Summarize the exemplar trace abc123...` |
| **Tool** | `tempo_summarize_trace` |
| **Parameters** | `{"backend_id": "default", "trace_id": "<exemplar_trace_id>"}` |

---

## Phase 6: Cross-Pillar Pivot — Logs to Traces

### Step 6.1: Extract Trace from a Log Line

| Field | Value |
|-------|-------|
| **Prompt** | `Extract and retrieve the trace from this log: "trace_id=abc123def456789012345678abcdef01 order processing failed"` |
| **Tool** | `tempo_get_trace_from_log` |
| **Parameters** | `{"backend_id": "default", "log_line": "trace_id=abc123def456789012345678abcdef01 order processing failed"}` |
| **Internal action** | (1) Parses the log line using regex patterns: `trace_id=`, `traceId:`, `TraceID=`, standalone 32-char hex. (2) Validates the extracted trace ID. (3) Fetches the full trace from Tempo. (4) Generates a summary. |
| **Expected output** | `{"extracted_trace_id": "abc123def456789012345678abcdef01", "extraction_method": "trace_id=", "log_line": "...", "trace_summary": {"headline": "...", "critical_path": [...], ...}}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `extracted_trace_id` | The 32-char hex trace ID parsed from the log |
| `extraction_method` | Which regex pattern matched |
| `trace_summary` | Full trace analysis including critical path, errors, root cause |

### Supported Log Formats

| Format | Example |
|--------|---------|
| `trace_id=<hex>` | `trace_id=abc123def456789012345678abcdef01 payment failed` |
| `traceId:<hex>` | `traceId:abc123def456789012345678abcdef01 order timeout` |
| `TraceID=<hex>` | `TraceID=abc123def456789012345678abcdef01 connection refused` |
| Standalone 32-char hex | `abc123def456789012345678abcdef01 checkout error` |

---

## Phase 7: Investigate Anomalies

### Decision Tree Based on RED Metrics

| RED Finding | Tool Call | Intent |
|-------------|-----------|--------|
| High error rate | `tempo_traceql_search(service="checkout", status="error")` | Find concrete error traces |
| High P99 latency | `tempo_traceql_search(service="checkout", min_duration_ms=<threshold>)` | Find slow traces |
| Rate drop to zero | `tempo_get_diagnostics(backend_id="default")` | Check backend health |
| Sudden rate spike | `tempo_traceql_search(service="checkout", since="15m")` | Find traces during spike |
| Error rate + latency spike | `tempo_traceql_search(service="checkout", status="error", min_duration_ms=500)` | Find slow error traces |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Rate measured | `tempo_traceql_metrics_range` (rate) | Request rate over time |
| ✅ Errors measured | `tempo_traceql_metrics_range` (error rate, count) | Error rate and error count |
| ✅ Duration measured | `tempo_traceql_metrics_range` (P50, P99, histogram, avg) | Latency distribution |
| ✅ Instant snapshot taken | `tempo_traceql_metrics_instant` | Current error rate |
| ✅ Metrics → Traces pivot | `tempo_get_exemplar_traces` | Concrete traces from metrics |
| ✅ Logs → Traces pivot | `tempo_get_trace_from_log` | Trace extracted and summarized from log line |

**Next step →** [Schema Exploration](TEMPO_SCHEMA_EXPLORATION_TEST_GUIDE.md): Full cluster-wide exploration — backend discovery, diagnostics, attribute taxonomy, K8s mapping, and deployment topology.
