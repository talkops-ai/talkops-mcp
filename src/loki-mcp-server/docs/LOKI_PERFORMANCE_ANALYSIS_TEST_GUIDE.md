# Performance Analysis Test Guide — Loki MCP Server

**Phase 7 of 7** in the Loki end-to-end journey.
**Previous phase**: [Incident Response](LOKI_INCIDENT_RESPONSE_TEST_GUIDE.md)

> The final phase. After incident response (Phase 6), this phase performs a
> systematic RED (Rate, Errors, Duration) analysis using LogQL metric queries —
> request rate, error rate, and latency distribution — all derived from log data.

---

## Prerequisites (Completed in Earlier Phases)

| Component | Status |
|-----------|--------|
| ✅ Loki reachable | `loki://system/health` — healthy |
| ✅ Service has active streams | `get_active_series` — streams confirmed |
| ✅ Log fields discovered | `get_detected_fields` — latency/duration fields known |
| ✅ Metric queries verified | `execute_logql_instant` and `execute_logql_query` — metric mode working |

---

## The Starting Point

Phase 6 responded to an active incident. Now you want a systematic performance
analysis of a service. You need to answer:

1. **What's the current request rate?** — Total log throughput.
2. **What's the current error rate?** — Error logs per second.
3. **What's the error percentage?** — Error rate / request rate.
4. **How do these trend over time?** — Rate and error time series.
5. **What's the latency distribution?** — Average, P99, max from structured fields.

---

## Phase 1: Instant Rates (Current State)

### Step 1.1: Current Request Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What is the current request rate for "order-service"?` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "sum(rate({app=\"order-service\"} [5m]))"}` |
| **Internal action** | Calls `GET /loki/api/v1/query` at `time=now`. Returns scalar request rate (log lines per second). |
| **Expected output** | `{"result_type": "vector", "result": [{"metric": {}, "value": [<ts>, "12.5"]}], "warnings": []}` |

**Interpretation:** `12.5` means 12.5 log lines per second — this is the request throughput if each request produces one log line.

### Step 1.2: Current Error Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What is the current error rate for "order-service"?` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "sum(rate({app=\"order-service\"} |= \"error\" [5m]))"}` |
| **Expected output** | `{"result_type": "vector", "result": [{"metric": {}, "value": [<ts>, "0.3"]}]}` |

### Step 1.3: Error Percentage

| Field | Value |
|-------|-------|
| **Prompt** | `What percentage of "order-service" requests are errors?` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "sum(rate({app=\"order-service\"} |= \"error\" [5m])) / sum(rate({app=\"order-service\"} [5m])) * 100"}` |
| **Expected output** | `{"result_type": "vector", "result": [{"metric": {}, "value": [<ts>, "2.4"]}]}` |

**Interpretation:**
- `2.4` means 2.4% error rate
- < 1% → ✅ Healthy
- 1-5% → ⚠️ Elevated — investigate
- > 5% → ❌ Significant — incident worthy

### Step 1.4: Request Rate Per Endpoint

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the request rate per endpoint for "order-service".` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "sum by (path) (rate({app=\"order-service\"} | json [5m]))"}` |
| **Internal action** | Groups by the `path` field (requires `| json` parser). Returns rate per endpoint. |

---

## Phase 2: Rate Trends Over Time

### Step 2.1: Request Rate Trend

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the request rate for "order-service" over the last 6 hours.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "sum(rate({app=\"order-service\"} [5m]))", "start": "now-6h", "end": "now", "step": "5m"}` |
| **Internal action** | Calls `GET /loki/api/v1/query_range` with the metric query. Returns matrix with time series — one data point per 5-minute step. |
| **Expected output** | `{"result_type": "matrix", "series": [{"metric": {}, "values": [[<ts>, "<rate>"], ...]}], "total_series": 1, "warnings": []}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `result_type` | Should be `"matrix"` for metric queries |
| `values` | Time series data points — look for trends |
| `total_series` | 1 for a `sum()` query, N for `sum by (...)` |

### Step 2.2: Error Rate Trend

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the error rate for "order-service" over the last 6 hours.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "sum(rate({app=\"order-service\"} |= \"error\" [5m]))", "start": "now-6h", "step": "5m"}` |
| **Expected output** | Matrix time series with error rate per step |

### Step 2.3: Compare Request and Error Rate

Overlay both series to see error rate as a proportion of total traffic:

| Step | Query | Purpose |
|------|-------|---------|
| Request rate | `sum(rate({app="order-service"} [5m]))` | Total throughput |
| Error rate | `sum(rate({app="order-service"} |= "error" [5m]))` | Error throughput |
| Error % | `sum(rate({...} |= "error" [5m])) / sum(rate({...} [5m])) * 100` | Error percentage |

---

## Phase 3: Latency Analysis

### Step 3.1: Discover Latency Field

| Field | Value |
|-------|-------|
| **Prompt** | `What fields are available in "order-service" logs?` |
| **Tool** | `get_detected_fields` |
| **Parameters** | `{"query": "{app=\"order-service\"}"}` |
| **Internal action** | Returns fields. Look for latency-related fields: `latency_ms`, `duration`, `response_time`, `elapsed_ms`. |

**Common latency field names:**

| Field Name | Type | Notes |
|------------|------|-------|
| `latency_ms` | float/int | Milliseconds |
| `duration` | float | Seconds or milliseconds (check units) |
| `response_time` | float | Seconds |
| `elapsed_ms` | int | Milliseconds |

> **If no latency field exists:** Log-based latency analysis isn't possible — you'd need tracing (e.g., Tempo MCP Server). Skip to Phase 4.

### Step 3.2: Average Latency Over Time

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the average latency for "order-service" over the last 6 hours.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "avg_over_time({app=\"order-service\"} | json | unwrap latency_ms [5m])", "start": "now-6h", "step": "5m"}` |
| **Internal action** | Uses `unwrap` to extract the numeric `latency_ms` field, then computes `avg_over_time`. |
| **Expected output** | `{"result_type": "matrix", "series": [...], "total_series": 1}` |

### Step 3.3: P99 Latency Over Time

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the P99 latency for "order-service" over the last 6 hours.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "quantile_over_time(0.99, {app=\"order-service\"} | json | unwrap latency_ms [5m])", "start": "now-6h", "step": "5m"}` |
| **Internal action** | Uses `quantile_over_time` with 0.99 quantile for P99 latency. |

### Step 3.4: Max Latency Over Time

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the maximum latency for "order-service" over the last 6 hours.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "max_over_time({app=\"order-service\"} | json | unwrap latency_ms [5m])", "start": "now-6h", "step": "5m"}` |

### Step 3.5: Latency Comparison

Compare all three to understand the latency profile:

| Metric | Query | Meaning |
|--------|-------|---------|
| Average | `avg_over_time(...\|unwrap latency_ms [5m])` | Typical request latency |
| P99 | `quantile_over_time(0.99, ...\|unwrap latency_ms [5m])` | Tail latency (worst 1%) |
| Max | `max_over_time(...\|unwrap latency_ms [5m])` | Absolute worst case |

**Interpretation:**
- **P99 elevated, average normal** → Tail latency issue (specific code paths)
- **Both elevated** → Systemic issue affecting all requests
- **Max spike, others normal** → Outlier (GC pause, cold start)

---

## Phase 4: Throughput by Dimension

### Step 4.1: Rate by Status Code

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the request rate grouped by HTTP status code for "order-service".` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "sum by (status_code) (rate({app=\"order-service\"} | json [5m]))", "start": "now-6h", "step": "5m"}` |
| **Internal action** | Returns one time series per status code. |

### Step 4.2: Rate by Endpoint

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the request rate grouped by endpoint for "order-service".` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "sum by (path) (rate({app=\"order-service\"} | json [5m]))", "start": "now-6h", "step": "5m"}` |

---

## LogQL Metric Functions Reference

| Function | Purpose | Example |
|----------|---------|---------|
| `rate()` | Log lines per second | `rate({app="checkout"} [5m])` |
| `count_over_time()` | Total count in window | `count_over_time({app="checkout"} [5m])` |
| `avg_over_time()` | Average of unwrapped field | `avg_over_time({...} \| json \| unwrap latency_ms [5m])` |
| `sum_over_time()` | Sum of unwrapped field | `sum_over_time({...} \| json \| unwrap bytes_sent [5m])` |
| `max_over_time()` | Maximum of unwrapped field | `max_over_time({...} \| json \| unwrap latency_ms [5m])` |
| `min_over_time()` | Minimum of unwrapped field | `min_over_time({...} \| json \| unwrap latency_ms [5m])` |
| `quantile_over_time()` | Quantile of unwrapped field | `quantile_over_time(0.99, {...} \| json \| unwrap latency_ms [5m])` |
| `sum()` | Aggregate across series | `sum(rate({app="checkout"} [5m]))` |
| `sum by ()` | Aggregate with grouping | `sum by (app) (rate({...} [5m]))` |
| `topk()` | Top N series by value | `topk(5, sum by (app) (rate({...} [5m])))` |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool | Status |
|------|------|--------|
| ✅ Current request rate | `execute_logql_instant(rate)` | Throughput measured |
| ✅ Current error rate | `execute_logql_instant(rate + error)` | Error rate measured |
| ✅ Error percentage | `execute_logql_instant(error/total)` | Error % calculated |
| ✅ Request rate trend | `execute_logql_query(rate, 6h)` | Throughput over time |
| ✅ Error rate trend | `execute_logql_query(error rate, 6h)` | Error evolution over time |
| ✅ Average latency | `execute_logql_query(avg_over_time + unwrap)` | Typical latency measured |
| ✅ P99 latency | `execute_logql_query(quantile_over_time + unwrap)` | Tail latency measured |
| ✅ Throughput by dimension | `execute_logql_query(sum by)` | Per-endpoint/status breakdown |

---

## Journey Complete 🎉

You've completed all 7 phases of the Loki MCP Server end-to-end journey:

| Phase | Guide | What You Verified |
|-------|-------|-------------------|
| 1 | [Error Investigation](LOKI_ERROR_INVESTIGATION_TEST_GUIDE.md) | Discovery → errors → quantification |
| 2 | [Health Check](LOKI_HEALTH_CHECK_TEST_GUIDE.md) | Loki reachability → service validation → volume |
| 3 | [Log Structure](LOKI_LOG_STRUCTURE_TEST_GUIDE.md) | Fields → patterns → parser selection |
| 4 | [LogQL Builder](LOKI_LOGQL_BUILDER_TEST_GUIDE.md) | Intent → discovery → construction → execution |
| 5 | [Schema Exploration](LOKI_SCHEMA_EXPLORATION_TEST_GUIDE.md) | Labels → cardinality → formats → governance |
| 6 | [Incident Response](LOKI_INCIDENT_RESPONSE_TEST_GUIDE.md) | Broad sweep → impact → drill-down → trends |
| 7 | [Performance Analysis](LOKI_PERFORMANCE_ANALYSIS_TEST_GUIDE.md) | Rate → errors → latency → dimensions |

All 8 tools, 8 resources, and 5 prompts have been exercised across these workflows.
