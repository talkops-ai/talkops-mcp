# Incident Response Test Guide — Loki MCP Server

**Phase 6 of 7** in the Loki end-to-end journey.
**Previous phase**: [Schema Exploration](LOKI_SCHEMA_EXPLORATION_TEST_GUIDE.md)
**Next phase**: [Performance Analysis](LOKI_PERFORMANCE_ANALYSIS_TEST_GUIDE.md)

> There's an active incident. This phase skips the leisurely discovery workflow
> and goes straight to execution — fetching error logs across all services,
> quantifying error rates per service, drilling into the worst offender, and
> discovering error patterns.

---

## Prerequisites (Completed in Earlier Phases)

| Component | Status |
|-----------|--------|
| ✅ Loki reachable | `loki://system/health` — healthy |
| ✅ Label taxonomy known | `get_cluster_labels` — labels discovered |
| ✅ Query execution verified | `execute_logql_query` — queries return data |

---

## The Starting Point

There's an active production incident. Alerts are firing, users are complaining,
and you need answers fast. No time for full discovery — this workflow prioritizes
speed and breadth over depth.

You need to answer:

1. **What's happening right now?** — Error logs across all services.
2. **Which services are affected?** — Error rate per service.
3. **What's the worst service?** — Drill into the most impacted.
4. **What do the errors look like?** — Error patterns and structure.
5. **Is it getting better or worse?** — Current rate vs trend.

---

## Phase 1: Broad Error Sweep

### Step 1.1: Fetch All Production Errors

| Field | Value |
|-------|-------|
| **Prompt** | `Show me all error logs from the production namespace in the last 15 minutes.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{namespace=\"production\"} |= \"error\"", "start": "now-15m", "end": "now", "limit": 100}` |
| **Internal action** | (1) Validates stream selector. (2) Parses time range. (3) Validates time window. (4) Pre-checks cost. (5) Calls `GET /loki/api/v1/query_range`. (6) Formats log entries. Returns up to 100 error log lines across all production services. |
| **Expected output** | `{"result_type": "streams", "streams": [...], "total_lines": N, "truncated": false, "warnings": []}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `streams` | Log entries from multiple services — look at stream labels to identify affected services |
| `total_lines` | High count = widespread issue; low count = isolated |
| `truncated` | If `true`, the problem is bigger than 100 entries |

### Step 1.2: Critical Errors Only

| Field | Value |
|-------|-------|
| **Prompt** | `Show me critical error logs — "panic" or "fatal" — from production in the last 15 minutes.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{namespace=\"production\"} |~ \"(?i)(panic|fatal|CRITICAL)\"", "start": "now-15m", "limit": 50}` |
| **Internal action** | Uses regex line filter for case-insensitive matching of critical keywords. |

---

## Phase 2: Quantify Impact Per Service

### Step 2.1: Error Rate By Service

| Field | Value |
|-------|-------|
| **Prompt** | `What is the error rate per service in production right now?` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "sum by (app) (rate({namespace=\"production\"} |= \"error\" [5m]))"}` |
| **Internal action** | Calls `GET /loki/api/v1/query` with the instant metric query. Returns error rate per service as a vector. |
| **Expected output** | `{"result_type": "vector", "result": [{"metric": {"app": "checkout"}, "value": [<ts>, "0.5"]}, {"metric": {"app": "api-gateway"}, "value": [<ts>, "0.1"]}, ...], "warnings": []}` |

**Interpretation:**
- Sort by rate descending — highest rate = most impacted service
- Absolute rate vs baseline: is this higher than normal?
- Multiple services affected → potential infrastructure issue
- Single service → application-level bug

### Step 2.2: Top 5 Error Producers

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the top 5 services with the highest error rate in production.` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "topk(5, sum by (app) (rate({namespace=\"production\"} |= \"error\" [5m])))"}` |
| **Internal action** | Uses LogQL `topk()` function to return only the top 5 error-producing services. |

---

## Phase 3: Drill Into Worst Service

### Step 3.1: Fetch Detailed Error Logs

| Field | Value |
|-------|-------|
| **Prompt** | `Show me detailed error logs from the "checkout" service — parsed as JSON.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"checkout\"} |= \"error\" | json", "start": "now-15m", "limit": 50}` |
| **Internal action** | Fetches error logs with JSON parser applied. Returns structured entries with extracted fields. |

**What to look for in the logs:**
- Error messages — recurring patterns?
- Status codes — all 500s? Mix of 400s and 500s?
- Stack traces — same root cause?
- Timestamps — when did it start?

### Step 3.2: Filter by Specific Error

If the logs reveal a specific error pattern (e.g., "connection refused"):

| Field | Value |
|-------|-------|
| **Prompt** | `Show me "checkout" logs containing "connection refused" in the last 15 minutes.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"checkout\"} |= \"connection refused\"", "start": "now-15m", "limit": 50}` |

---

## Phase 4: Error Pattern Analysis

### Step 4.1: Discover Error Patterns

| Field | Value |
|-------|-------|
| **Prompt** | `What log patterns exist for "checkout" errors?` |
| **Tool** | `get_log_patterns` |
| **Parameters** | `{"query": "{app=\"checkout\"}", "start": "now-3h"}` |
| **Internal action** | Returns structural patterns from Loki's pattern ingester. Sorted by frequency. |
| **Expected output** | `{"patterns": [{"pattern": "<_> [ERROR] <_> connection refused <_>", "total_count": 1250}, ...], "total_patterns": N, "suggested_parsers": [...]}` |

**What to check:**
- Dominant pattern → this is the main error shape
- Multiple patterns → multiple error types in play
- Pattern count → severity indicator

---

## Phase 5: Trend Assessment

### Step 5.1: Current Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What is the current error rate for "checkout"?` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "sum(rate({app=\"checkout\"} |= \"error\" [1m]))"}` |
| **Internal action** | 1-minute rate for the most current picture. |

### Step 5.2: Error Rate Trend

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the error rate trend for "checkout" over the last hour.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "sum(rate({app=\"checkout\"} |= \"error\" [1m]))", "start": "now-1h", "step": "1m"}` |
| **Internal action** | Returns 1-minute resolution time series showing the error rate evolution. |

**Interpretation:**

| Pattern | Meaning |
|---------|---------|
| Spike then flat at high rate | Error started at a specific time, ongoing |
| Spike then declining | Error is self-recovering (e.g., transient issue) |
| Gradually increasing | Cascading failure or resource exhaustion |
| Flat at normal level | False alarm or issue already resolved |

---

## Incident Response Quick Reference

### Common Incident Queries

| Purpose | LogQL |
|---------|-------|
| All errors in production | `{namespace="production"} |= "error"` |
| Critical errors only | `{namespace="production"} |~ "(?i)(panic\|fatal\|CRITICAL)"` |
| Error rate per service | `sum by (app) (rate({namespace="production"} |= "error" [5m]))` |
| Top 5 error producers | `topk(5, sum by (app) (rate({namespace="production"} |= "error" [5m])))` |
| Specific error pattern | `{app="checkout"} |= "connection refused"` |
| Error rate with 1m resolution | `sum(rate({app="checkout"} |= "error" [1m]))` |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool | Status |
|------|------|--------|
| ✅ Broad error sweep | `execute_logql_query(|= "error")` | All production errors seen |
| ✅ Impact quantified per service | `execute_logql_instant(sum by app)` | Error rate per service known |
| ✅ Worst service identified | `topk(5, ...)` | Top error producers ranked |
| ✅ Detailed error logs reviewed | `execute_logql_query(| json)` | Concrete error patterns found |
| ✅ Error patterns discovered | `get_log_patterns` | Recurring shapes identified |
| ✅ Trend assessed | `execute_logql_query(rate)` | Getting better or worse — known |

**Next step →** [Performance Analysis](LOKI_PERFORMANCE_ANALYSIS_TEST_GUIDE.md): Analyze request rate, error rate, and latency distribution using LogQL metric queries.
