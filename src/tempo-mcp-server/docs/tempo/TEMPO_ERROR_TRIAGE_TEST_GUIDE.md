# Error Triage Test Guide — Tempo MCP Server (OTel Demo)

**Phase 1 of 7** in the Tempo end-to-end journey.
**Next phase**: [Latency Investigation](TEMPO_LATENCY_INVESTIGATION_TEST_GUIDE.md)

> A service is producing errors. This phase walks through quantifying the error rate,
> comparing with baseline, finding concrete error traces, analyzing root cause via
> trace summarization, and correlating with related error traces — using a metrics-first approach.
>
> **Target service**: `checkout` — order processing service that calls payment, shipping, and cart.

---

## Prerequisites

| Component | Status |
|-----------|--------|
| Tempo backend | v2.7+ accessible via HTTP at `TEMPO_BASE_URL` (metrics-generator with `local-blocks` enabled) |
| MCP Server | Running (`uv run tempo-mcp-server`) |
| OTel Demo apps | 16 services in `otel-demo` namespace, instrumented via OTel Operator |
| OTel Collector | `otel-demo-collector` DaemonSet exporting traces to Tempo via `otlp/grpc` |
| Backend ID | `default` — auto-configured from `TEMPO_BASE_URL` |

---

## The Starting Point

You've received an alert that the `checkout` service is producing errors during order processing.
You need to answer:

1. **How bad is it?** — Quantify the error rate with metrics.
2. **Is it getting worse?** — Compare error rate with overall request rate.
3. **What are the errors?** — Find concrete error traces.
4. **What caused it?** — Analyze the root cause via trace summarization.
5. **Is it widespread?** — Correlate with related error traces.
6. **Is the backend healthy?** — Verify Tempo itself isn't degraded.

---

## Phase 1: Quantify Impact (Metrics-First)

### Step 1.1: Check Error Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What's the error rate for "checkout" over the last hour?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" && status = error } | rate()", "since": "1h"}` |
| **Internal action** | Validates TraceQL syntax. Resolves `since=1h` to epoch timestamps. Validates time range against `TEMPO_MAX_METRICS_DURATION`. Calls `GET /api/metrics/query_range`. Returns Prometheus-compatible time series. |
| **Expected output** | `{"effective_query": "...", "result_type": "matrix", "series": [{"labels": {}, "points": [{"ts": <epoch>, "value": "<rate>"}]}]}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `result_type` | Should be `"matrix"` — time series data |
| `series` | Should contain at least one series with data points |
| `points` | Values > 0 confirm errors are occurring |

> **Note**: If you get an error about "empty ring" or "generator", the metrics-generator is not configured. Use `tempo_get_diagnostics` to verify.

### Step 1.2: Compare with Baseline Request Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What's the total request rate for "checkout" over the last hour?` |
| **Tool** | `tempo_traceql_metrics_range` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" } | rate()", "since": "1h"}` |
| **Internal action** | Same as Step 1.1 but without `status = error` filter. Returns total span rate. |

**Interpretation:**
- Error rate / total rate = Error percentage
- If error rate is > 5% of total → significant incident
- If error rate is < 1% → likely transient or expected failures

---

## Phase 2: Find Error Traces

### Step 2.1: Search for Error Traces

| Field | Value |
|-------|-------|
| **Prompt** | `Find error traces from "checkout" in the last 30 minutes.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "service": "checkout", "status": "error", "since": "30m"}` |
| **Internal action** | (1) Builds TraceQL from K8s-friendly filters: `{ resource.service.name = "checkout" && status = error }`. (2) Validates TraceQL. (3) Resolves time range. (4) Enforces limit from query policy. (5) Calls `GET /api/search`. (6) Normalizes response. |
| **Expected output** | `{"effective_query": "{ resource.service.name = \"checkout\" && status = error }", "traces": [{"trace_id": "...", "root_service": "frontend", "root_span": "GET /api/cart/checkout", "duration_ms": 1234, "span_sets_count": 1}], "truncated": false, "total_matched": N}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `effective_query` | Should contain `resource.service.name = "checkout"` and `status = error` |
| `traces` | List of matching traces with trace IDs |
| `trace_id` | 32-char hex string — used in subsequent steps |
| `root_service` | May be `frontend` (traces often start at the edge) |
| `truncated` | If `true`, there are more traces than the limit — narrow time range |
| `determinism_note` | Reminder that Tempo search is non-deterministic |

### Step 2.2: Search with Raw TraceQL

| Field | Value |
|-------|-------|
| **Prompt** | `Find checkout error traces with HTTP 500 status codes.` |
| **Tool** | `tempo_traceql_search` |
| **Parameters** | `{"backend_id": "default", "query": "{ resource.service.name = \"checkout\" && span.http.status_code >= 500 }", "since": "1h"}` |
| **Internal action** | Uses raw TraceQL directly. Same guardrails applied. |

---

## Phase 3: Analyze Root Cause

### Step 3.1: Summarize the First Error Trace

| Field | Value |
|-------|-------|
| **Prompt** | `Summarize trace abc123def456789012345678abcdef01.` |
| **Tool** | `tempo_summarize_trace` |
| **Parameters** | `{"backend_id": "default", "trace_id": "<trace_id_from_step_2>"}` |
| **Internal action** | (1) Validates trace ID (16-32 hex chars). (2) Fetches full trace in OTLP format. (3) Extracts critical path (longest chain from root to leaf). (4) Identifies error spans. (5) Detects K8s context. (6) Generates headline. (7) Recommends next queries. |
| **Expected output** | `{"trace_id": "...", "headline": "checkout → payment error: connection refused", "critical_path": [{"service": "frontend", "span_name": "GET /api/cart/checkout", "duration_ms": 1234}, ...], "errors": [{"service": "payment", "span_name": "oteldemo.PaymentService/Charge", "status_message": "connection refused"}], "suspected_root_cause": "payment service unreachable", "recommended_next_queries": ["{ resource.service.name = \"payment\" && status = error }"]}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `headline` | One-line summary of what happened |
| `critical_path` | Ordered list of services/spans in the longest execution path |
| `errors` | List of error spans with service, span name, and status message |
| `suspected_root_cause` | AI-generated root cause hypothesis |
| `recommended_next_queries` | Follow-up TraceQL queries to continue investigation |

---

## Phase 4: Correlate with Related Traces

### Step 4.1: Find Related Error Traces

| Field | Value |
|-------|-------|
| **Prompt** | `Find traces related to <trace_id> with the same service errors.` |
| **Tool** | `tempo_find_related_traces` |
| **Parameters** | `{"backend_id": "default", "trace_id": "<trace_id_from_step_2>", "correlation_strategy": "same_service_errors", "since": "1h", "limit": 5}` |
| **Internal action** | (1) Fetches seed trace. (2) Extracts error service from summary. (3) Builds correlation query: `{ resource.service.name = "<error_service>" && status = error }`. (4) Searches for matching traces. (5) Excludes seed trace from results. |
| **Expected output** | `{"seed_trace_id": "...", "strategy": "same_service_errors", "related_traces": [{"trace_id": "...", "root_service": "frontend", "root_span": "...", "duration_ms": 987}], "effective_query": "{ resource.service.name = \"payment\" && status = error }", "total_found": N}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `strategy` | Should be `"same_service_errors"` |
| `related_traces` | Traces with the same error pattern |
| `total_found` | If 0, try `same_endpoint` or `temporal_neighbors` strategy |
| `strategy_note` | If present, indicates the chosen strategy couldn't be applied |

### Step 4.2: Alternative Strategy — Same Endpoint

| Field | Value |
|-------|-------|
| **Prompt** | `Find traces that hit the same endpoint as <trace_id>.` |
| **Tool** | `tempo_find_related_traces` |
| **Parameters** | `{"backend_id": "default", "trace_id": "<trace_id>", "correlation_strategy": "same_endpoint", "since": "1h"}` |

---

## Phase 5: Contextualize

### Step 5.1: Check Backend Health

| Field | Value |
|-------|-------|
| **Prompt** | `Run diagnostics on the "default" Tempo backend.` |
| **Tool** | `tempo_get_diagnostics` |
| **Parameters** | `{"backend_id": "default"}` |
| **Internal action** | Aggregates: (1) Health check (`/ready`). (2) Build info (`/api/status/buildinfo`). (3) Service status (`/status/services`). (4) Ring checks (if deployment mode is configured). Produces severity-ranked findings. |
| **Expected output** | `{"status": "healthy", "ready": true, "deployment_mode": "unknown", "build_info": {...}, "services": {...}, "findings": [...], "issues": 0}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `status` | `"healthy"` = all clear; `"degraded"` = some issues; `"unhealthy"` = critical |
| `ready` | Should be `true` |
| `findings` | List of severity-ranked findings with suggested actions |
| `issues` | Count of warning/critical findings |

### Step 5.2: Consult Error Burst Runbook

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the error burst investigation runbook.` |
| **Resource** | `tempo://runbooks/error-burst` |
| **Internal action** | Returns static markdown with the error burst investigation workflow |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Error rate quantified | `tempo_traceql_metrics_range` | Error rate measured over time, compared with baseline |
| ✅ Error traces found | `tempo_traceql_search` | Concrete error traces with trace IDs |
| ✅ Root cause analyzed | `tempo_summarize_trace` | Critical path, error spans, suspected root cause identified |
| ✅ Related traces correlated | `tempo_find_related_traces` | Similar error traces found for pattern analysis |
| ✅ Backend health verified | `tempo_get_diagnostics` | Tempo itself is not the issue |

**Next step →** [Latency Investigation](TEMPO_LATENCY_INVESTIGATION_TEST_GUIDE.md): Confirm a P99 latency spike, find slow traces, analyze the critical path, and compare slow vs normal traces.
