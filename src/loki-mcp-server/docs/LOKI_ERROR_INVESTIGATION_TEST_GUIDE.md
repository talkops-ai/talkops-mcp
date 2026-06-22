# Error Investigation Test Guide — Loki MCP Server

**Phase 1 of 7** in the Loki end-to-end journey.
**Next phase**: [Service Health Check](LOKI_HEALTH_CHECK_TEST_GUIDE.md)

> A service is producing errors. This phase walks through discovering the label taxonomy,
> finding the service, validating the selector, discovering log structure, pre-checking
> query cost, fetching error logs, and quantifying error rate — all using the Loki MCP server tools.

---

## Prerequisites

| Component | Status |
|-----------|--------|
| Loki backend | Accessible via HTTP at configured `LOKI_URL` |
| MCP Server | Running (`uv run loki-mcp-server`) |
| Services instrumented | At least one service sending logs to Loki |

---

## The Starting Point

You've received an alert or a user report that the `checkout-service` is throwing errors.
You need to answer:

1. **What labels exist?** — Discover the label taxonomy so you don't guess.
2. **Does the service exist?** — Confirm the service name is valid.
3. **Does the selector match?** — Validate that the selector matches active streams.
4. **What's the log structure?** — Discover fields, types, and the correct parser.
5. **Is the query safe?** — Pre-check cost before executing.
6. **What are the error logs?** — Fetch concrete error log lines.
7. **How bad is it?** — Quantify the error rate.

---

## Phase 1: Label Discovery

### Step 1.1: Discover Available Labels

| Field | Value |
|-------|-------|
| **Prompt** | `What labels are available in my Loki cluster?` |
| **Tool** | `get_cluster_labels` |
| **Parameters** | `{}` |
| **Internal action** | Calls `GET /loki/api/v1/labels`. Returns all label names currently present in Loki. |
| **Expected output** | `{"labels": ["app", "cluster", "env", "namespace", ...], "count": N}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `labels` | Should contain expected labels like `app`, `namespace`, `env` |
| `count` | Non-zero — confirms data is being ingested |

### Step 1.2: Find Service Names

| Field | Value |
|-------|-------|
| **Prompt** | `What services are sending logs to Loki?` |
| **Tool** | `get_label_values` |
| **Parameters** | `{"label": "app"}` |
| **Internal action** | Calls `GET /loki/api/v1/label/app/values`. Returns all distinct values for the `app` label. |
| **Expected output** | `{"label": "app", "values": ["checkout", "api-gateway", "payment-service", ...], "count": N}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `values` | Should contain `checkout` (or your target service name) |
| `count` | Number of distinct services |

> **If `app` label doesn't exist:** Try `get_label_values(label="service_name")` or `get_label_values(label="job")`.

---

## Phase 2: Selector Validation

### Step 2.1: Validate the Service Selector

| Field | Value |
|-------|-------|
| **Prompt** | `Validate that the selector '{app="checkout"}' matches active log streams.` |
| **Tool** | `get_active_series` |
| **Parameters** | `{"match": "{app=\"checkout\"}"}` |
| **Internal action** | Calls `GET /loki/api/v1/series?match[]={app="checkout"}`. Returns matching series with per-label cardinality and high-cardinality warnings. |
| **Expected output** | `{"matcher": "{app=\"checkout\"}", "total_series": N, "series": [...], "label_cardinality": {...}, "warnings": [...]}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `total_series` | Should be > 0 — confirms the selector matches real streams |
| `label_cardinality` | Per-label unique value count. High values (> 10,000) trigger warnings |
| `warnings` | Any high-cardinality warnings — labels exceeding threshold should NOT be used in `{}` stream selectors |

---

## Phase 3: Log Structure Discovery

### Step 3.1: Discover Structured Fields

| Field | Value |
|-------|-------|
| **Prompt** | `What fields can I query in "checkout" logs?` |
| **Tool** | `get_detected_fields` |
| **Parameters** | `{"query": "{app=\"checkout\"}"}` |
| **Internal action** | Calls `GET /loki/api/v1/detected_fields?query={app="checkout"}`. Returns JSON/logfmt field names, types, cardinality, and required parsers. |
| **Expected output** | `{"fields": [{"label": "level", "type": "string", "cardinality": 4, "parsers": ["json"]}, ...], "total_fields": N}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `fields` | List of discovered fields — look for `level`, `msg`, `status_code`, `latency_ms` |
| `parsers` | Which parser(s) to use: `["json"]`, `["logfmt"]`, or `["json", "logfmt"]` |
| `type` | Field types: `string`, `int`, `float` |
| `total_fields` | Non-zero — confirms logs have structured content |

**Interpretation:**
- Fields with `parsers: ["json"]` → Use `| json` in LogQL pipeline
- Fields with `parsers: ["logfmt"]` → Use `| logfmt` in LogQL pipeline
- No fields → Logs are unstructured plain text. Use `| pattern` or line filters.

---

## Phase 4: Cost Preflight

### Step 4.1: Estimate Query Cost

| Field | Value |
|-------|-------|
| **Prompt** | `How expensive would it be to query '{app="checkout"}' for the last hour?` |
| **Tool** | `get_query_stats` |
| **Parameters** | `{"query": "{app=\"checkout\"}", "start": "now-1h"}` |
| **Internal action** | Calls `GET /loki/api/v1/index/stats?query={app="checkout"}&start=<epoch>`. Returns streams, chunks, entries, and total bytes. Compares bytes against `LOKI_MAX_QUERY_BYTES` threshold. |
| **Expected output** | `{"streams": N, "chunks": N, "entries": N, "bytes": N, "human_bytes": "X.XX MB", "exceeds_threshold": false, "threshold_bytes": 5000000000}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `exceeds_threshold` | Should be `false` — if `true`, narrow the time range or add more selectors |
| `human_bytes` | Human-readable cost estimate (e.g., "12.50 MB" vs "3.20 GB") |
| `streams` | Number of log streams that match |

---

## Phase 5: Execute Error Queries

### Step 5.1: Fetch Error Logs

| Field | Value |
|-------|-------|
| **Prompt** | `Show me error logs from "checkout" in the last hour.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"checkout\"} |= \"error\" | json", "start": "now-1h", "end": "now", "limit": 100}` |
| **Internal action** | (1) Validates stream selector syntax. (2) Detects high-cardinality labels in selector. (3) Parses relative timestamps to epoch. (4) Validates time window against `LOKI_MAX_TIME_WINDOW_HOURS`. (5) Pre-checks cost via index stats. (6) Clamps limit to `LOKI_MAX_LOG_LIMIT`. (7) Calls `GET /loki/api/v1/query_range`. (8) Formats log entries. |
| **Expected output** | `{"result_type": "streams", "streams": [...], "total_lines": N, "truncated": false, "warnings": []}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `result_type` | Should be `"streams"` for log queries |
| `streams` | Should contain log entries with timestamps and log lines |
| `total_lines` | Number of log lines returned |
| `truncated` | If `true`, there are more logs than the limit — narrow the time range |
| `warnings` | Any high-cardinality warnings |

### Step 5.2: Search with Specific LogQL

| Field | Value |
|-------|-------|
| **Prompt** | `Search for logs matching '{app="checkout"} | json | level="error" | status_code >= 500' in the last hour.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"checkout\"} | json | level=\"error\" | status_code >= 500", "start": "now-1h", "limit": 50}` |
| **Internal action** | Uses the full LogQL query directly with parser and label filter stages. |

---

## Phase 6: Quantify Impact

### Step 6.1: Current Error Rate

| Field | Value |
|-------|-------|
| **Prompt** | `What is the current error rate for "checkout"?` |
| **Tool** | `execute_logql_instant` |
| **Parameters** | `{"query": "sum(rate({app=\"checkout\"} |= \"error\" [5m]))"}` |
| **Internal action** | Calls `GET /loki/api/v1/query` with the metric query at `time=now`. Returns a scalar vector result. |
| **Expected output** | `{"result_type": "vector", "result": [{"metric": {}, "value": [<timestamp>, "<rate>"]}], "warnings": []}` |

### Step 6.2: Error Rate Over Time

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the error rate over time for "checkout" in the last hour.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "sum(rate({app=\"checkout\"} |= \"error\" [5m]))", "start": "now-1h", "step": "5m"}` |
| **Internal action** | Calls `GET /loki/api/v1/query_range` with the metric query. Returns a matrix result with time series. |
| **Expected output** | `{"result_type": "matrix", "series": [{"metric": {}, "values": [[<ts>, "<rate>"], ...]}], "total_series": 1, "warnings": []}` |

**Interpretation:**
- Error rate spike at a specific time → recent regression
- Steady elevated error rate → persistent issue
- Error rate / total rate = Error percentage. If > 5% → significant incident.

---

## Phase 7: Consult References

### Step 7.1: LogQL Syntax Reference

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the LogQL syntax reference.` |
| **Resource** | `loki://reference/logql` |
| **Internal action** | Returns static markdown with LogQL syntax guide |

### Step 7.2: Query Templates

| Field | Value |
|-------|-------|
| **Prompt** | `Show me common LogQL query templates.` |
| **Resource** | `loki://reference/query-templates` |
| **Internal action** | Returns common incident, debug, audit, and performance query patterns |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Labels discovered | `get_cluster_labels` | Label taxonomy known |
| ✅ Service found | `get_label_values(label="app")` | Service name confirmed |
| ✅ Selector validated | `get_active_series` | Streams exist, cardinality assessed |
| ✅ Log structure discovered | `get_detected_fields` | Fields, types, parsers known |
| ✅ Query cost pre-checked | `get_query_stats` | Cost within threshold |
| ✅ Error logs fetched | `execute_logql_query(|= "error")` | Concrete error log lines |
| ✅ Error rate quantified | `execute_logql_instant(rate(...))` | Error rate measured |

**Next step →** [Service Health Check](LOKI_HEALTH_CHECK_TEST_GUIDE.md): Verify Loki reachability and validate that a service's log pipeline is healthy.
