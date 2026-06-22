# Latency Investigation Test Guide — Tempo MCP Server (OTel Demo)

**Phase 2 of 7** in the Tempo end-to-end journey.
**Previous phase**: [Error Triage](TEMPO_ERROR_TRIAGE_TEST_GUIDE.md)
**Next phase**: [Missing Traces Diagnostic](TEMPO_MISSING_TRACES_TEST_GUIDE.md)

> The `frontend` service is experiencing latency spikes. This phase confirms the spike
> with P99 metrics, finds slow traces, analyzes the critical path via trace summarization,
> finds normal traces for comparison, and performs a 5-dimensional trace diff.
>
> **Target service**: `frontend` — JavaScript HTTP server that calls checkout, recommendation, ad, and product-catalog.

---

## Prerequisites (Completed in Phase 1)

| Component | Status |
|-----------|--------|
| ✅ Tempo backend accessible | `tempo_get_diagnostics` — healthy |
| ✅ MCP server running | HTTP transport on `http://localhost:8768/mcp` |
| ✅ OTel Demo traces flowing | `tempo_traceql_search` — traces found |
| ✅ Metrics-generator working | `tempo_traceql_metrics_range` — time series returned |

---

## The Starting Point

Phase 1 triaged errors. Now you're investigating a latency spike — the frontend service is slow.
You need to answer:

1. **Is the spike real?** — Confirm with P99 latency metrics over time.
2. **When did it start?** — Identify the spike window from the time series.
3. **Which traces are slow?** — Find traces above the latency threshold.
4. **Where is the bottleneck?** — Analyze the critical path in a slow trace.
5. **What changed?** — Compare a slow trace against a normal one to find the regression.

---

## Phase 1: Confirm the Spike

### Step 1.1: P99 Latency Trend

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the P99 latency trend for "frontend" in the last 6 hours.` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"frontend\" } | quantile_over_time(duration, 0.99)", "since": "6h"}` |
| **Internal action** | Validates TraceQL syntax. Resolves `since=6h` to epoch timestamps. Clamps to `TEMPO_MAX_METRICS_DURATION` (default 3h — if 6h exceeds, the server will clamp or error). Calls `GET /api/metrics/query_range`. |
| **Expected output** | `{"effective_query": "...", "result_type": "matrix", "series": [{"labels": {}, "points": [{"ts": <epoch>, "value": "<p99_ms>"}]}]}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `result_type` | `"matrix"` — time series |
| `points` | Look for values significantly above baseline (e.g., > 500ms when normal is < 200ms) |
| `time range` | If clamped, the `effective_time_range` field will show the actual range used |

> **Note**: If the time range exceeds `TEMPO_MAX_METRICS_DURATION`, reduce `since` to `"3h"` or check current limits via `tempo_get_query_policies`.

### Step 1.2: Duration Histogram

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the duration distribution for "frontend" traces.` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"frontend\" } | histogram_over_time(duration)", "since": "1h"}` |
| **Internal action** | Returns bucketed histogram of span durations. |

---

## Phase 2: Find Slow Traces

### Step 2.1: Search for Traces Above Threshold

| Field | Value |
|-------|-------|
| **Prompt** | `Find traces from "frontend" above 500ms in the last hour.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "service": "frontend", "min_duration_ms": 500, "since": "1h"}` |
| **Internal action** | Builds TraceQL: `{ resource.service.name = "frontend" && duration > 500ms }`. Validates, resolves time, enforces limits. Calls `GET /api/search`. |
| **Expected output** | `{"effective_query": "{ resource.service.name = \"frontend\" && duration > 500ms }", "traces": [{"trace_id": "...", "root_service": "frontend", "root_span": "GET /api/products", "duration_ms": 2341}], "total_matched": N}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `traces` | Sort by `duration_ms` descending to find the slowest |
| `root_span` | Which operation is slow? (e.g., `GET /api/products`, `GET /api/cart/checkout`) |
| `total_matched` | How many traces exceeded the threshold |

### Step 2.2: Search with Raw TraceQL (Structural)

| Field | Value |
|-------|-------|
| **Prompt** | `Find traces where frontend calls checkout and the checkout span is slow.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"frontend\" } >> { resource.service.name = \"checkout\" && duration > 1s }", "since": "1h"}` |
| **Internal action** | Uses structural `>>` operator. Requires Tempo 2.4+. |

---

## Phase 3: Critical Path Analysis

### Step 3.1: Summarize the Slowest Trace

| Field | Value |
|-------|-------|
| **Prompt** | `Summarize the slowest trace from the search results.` |
| **Tool** | `tempo_summarize_trace` |
| **Parameters** | `{"backend_id": "default", "trace_id": "<slowest_trace_id_from_step_2>"}` |
| **Internal action** | Fetches full trace (attempts LLM format first, falls back to OTLP). Builds span tree. Extracts critical path. Identifies error spans. Detects time gaps (wall-clock vs critical-path disambiguation). |
| **Expected output** | `{"trace_id": "...", "headline": "frontend → checkout → payment slow: 2341ms total, payment charge took 1800ms", "critical_path": [...], "errors": [...], "time_gap_detected": false, "suspected_root_cause": "payment service latency", "recommended_next_queries": [...]}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `headline` | Quick summary — identifies the bottleneck |
| `critical_path` | The ordered sequence of spans that constitutes the longest execution chain |
| `critical_path[i].duration_ms` | Where does the time accumulate? |
| `time_gap_detected` | If `true`, there are async/disjointed spans — trace duration > sum of critical path |
| `suspected_root_cause` | Which service/span is the bottleneck? |
| `recommended_next_queries` | Follow-up queries targeting the bottleneck service |

### Critical Path Interpretation

| Pattern | Meaning | Next Action |
|---------|---------|-------------|
| Single downstream service dominates | That service is the bottleneck | Investigate that service: `tempo_summarize_trace` on a trace from that service |
| Multiple services each contribute ~equally | Parallelism issue or sequential calls that should be concurrent | Review orchestration logic |
| Time gap between spans | Async/queue delay or scheduling | Check message broker or scheduler |
| Root span is slow but no downstream | CPU/memory bottleneck in the root service | Check resource limits |

---

## Phase 4: Compare with Normal Traces

### Step 4.1: Find Normal Traces

| Field | Value |
|-------|-------|
| **Prompt** | `Find normal-speed traces from "frontend" under 250ms.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "service": "frontend", "max_duration_ms": 250, "since": "1h", "limit": 3}` |
| **Internal action** | Builds: `{ resource.service.name = "frontend" && duration < 250ms }`. |

### Step 4.2: Compare Slow vs Normal Trace

| Field | Value |
|-------|-------|
| **Prompt** | `Compare the normal trace <normal_id> against the slow trace <slow_id>.` |
| **Tool** | `tempo_compare_traces` |
| **Parameters** | `{"backend_id": "default", "trace_id_a": "<normal_trace_id>", "trace_id_b": "<slow_trace_id>"}` |
| **Internal action** | (1) Validates both trace IDs (32-char hex). (2) Ensures they're different. (3) Fetches both traces. (4) Builds span trees. (5) Computes 5-dimensional diff: structural (services), span counts, timing, errors, attributes. |
| **Expected output** | `{"trace_a": {"trace_id": "...", "services": [...], "total_spans": N, "duration_ms": 200}, "trace_b": {..., "duration_ms": 2341}, "structural_diff": {"services_only_in_a": [], "services_only_in_b": ["external-api"], "common_services": [...]}, "span_count_diff": {...}, "duration_diff": {"a_duration_ms": 200, "b_duration_ms": 2341, "delta_ms": 2141}, "error_diff": {...}, "attribute_diff": {...}}` |

**What to check:**

| Diff Dimension | What to Look For |
|----------------|------------------|
| `structural_diff.services_only_in_b` | A new downstream service appeared in the slow trace |
| `span_count_diff` | Significantly more spans in the slow trace → N+1 query problem |
| `duration_diff.delta_ms` | How much slower? Where does the delta come from? |
| `error_diff` | Errors only in the slow trace → the latency is from retries |
| `attribute_diff` | Different attribute values (e.g., different HTTP method, different endpoint) |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ P99 spike confirmed | `tempo_traceql_metrics_range` | Latency spike visible in time series |
| ✅ Slow traces found | `tempo_traceql_search` | Traces above threshold identified |
| ✅ Critical path analyzed | `tempo_summarize_trace` | Bottleneck service/span identified |
| ✅ Normal vs slow compared | `tempo_compare_traces` | 5-dimensional diff shows what changed |

**Next step →** [Missing Traces Diagnostic](TEMPO_MISSING_TRACES_TEST_GUIDE.md): Diagnose why traces aren't showing up — verify backend health, data existence, and scope configuration.
