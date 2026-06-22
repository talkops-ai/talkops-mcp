# Service Health Check Test Guide — Loki MCP Server

**Phase 2 of 7** in the Loki end-to-end journey.
**Previous phase**: [Error Investigation](LOKI_ERROR_INVESTIGATION_TEST_GUIDE.md)
**Next phase**: [Log Structure Analysis](LOKI_LOG_STRUCTURE_TEST_GUIDE.md)

> After investigating errors (Phase 1), this phase verifies that Loki is reachable,
> the label taxonomy is intact, the target service has active streams, and logs are
> being ingested at expected rates.

---

## Prerequisites (Completed in Phase 1)

| Component | Status |
|-----------|--------|
| ✅ Labels discovered | `get_cluster_labels()` — labels returned |
| ✅ Label values fetched | `get_label_values` — service names known |
| ✅ Selector validated | `get_active_series` — streams confirmed |

---

## The Starting Point

Phase 1 investigated errors. Now you want to verify the overall health of the log pipeline.
You need to answer:

1. **Is Loki healthy?** — Verify reachability and readiness.
2. **Is the label taxonomy intact?** — Confirm expected labels exist.
3. **Is the service producing logs?** — Validate active streams.
4. **What's the ingestion rate?** — Check recent log volume.
5. **Are recent logs arriving?** — Fetch the latest log lines.

---

## Phase 1: System Health

### Step 1.1: Check Loki Reachability

| Field | Value |
|-------|-------|
| **Prompt** | `Is Loki reachable and healthy?` |
| **Resource** | `loki://system/health` |
| **Internal action** | Calls `GET /ready` and `GET /loki/api/v1/labels` to check reachability and verify data exists. Returns health status and label count. |
| **Expected output** | `{"status": "ready", "label_count": N, "reachable": true}` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `reachable` | Should be `true` — Loki responds to HTTP requests |
| `status` | Should be `"ready"` — Loki is accepting queries |
| `label_count` | Should be > 0 — data is being ingested |

**Common failure modes:**

| Failure | Meaning | Fix |
|---------|---------|-----|
| `reachable: false` | Loki is down or unreachable | Check `LOKI_URL` and Loki deployment |
| `label_count: 0` | No data ingested | Check ingestion pipeline (OTel Collector → Loki) |

---

## Phase 2: Label Taxonomy Verification

### Step 2.1: Verify Labels Exist

| Field | Value |
|-------|-------|
| **Prompt** | `List all label names in Loki.` |
| **Tool** | `get_cluster_labels` |
| **Parameters** | `{}` |
| **Internal action** | Calls `GET /loki/api/v1/labels`. Returns all label names. |
| **Expected output** | `{"labels": ["app", "cluster", "env", "namespace", ...], "count": N}` |

**What to check:**
- Expected labels like `app`, `namespace`, `env`, `cluster` should be present.
- If critical labels are missing, the ingestion pipeline may be misconfigured.

### Step 2.2: Check Schema Resource

| Field | Value |
|-------|-------|
| **Prompt** | `Show me all label names in the Loki schema.` |
| **Resource** | `loki://schema/labels` |
| **Internal action** | Returns all label names and count as JSON |

---

## Phase 3: Service Validation

### Step 3.1: Validate Service Streams

| Field | Value |
|-------|-------|
| **Prompt** | `Validate that '{app="payment-service"}' has active log streams.` |
| **Tool** | `get_active_series` |
| **Parameters** | `{"match": "{app=\"payment-service\"}"}` |
| **Internal action** | Calls `GET /loki/api/v1/series`. Returns matching series with per-label cardinality. |
| **Expected output** | `{"matcher": "{app=\"payment-service\"}", "total_series": N, "series": [...], "label_cardinality": {...}, "warnings": [...]}` |

**Interpretation:**

| `total_series` | Meaning | Next Action |
|----------------|---------|-------------|
| > 0 | ✅ Service is producing logs | Proceed to volume check |
| 0 | ⚠️ No active streams | Try different label (e.g., `service_name` or `job`) |

---

## Phase 4: Volume Check

### Step 4.1: Check Recent Log Volume

| Field | Value |
|-------|-------|
| **Prompt** | `How much log data does "payment-service" have in the last hour?` |
| **Tool** | `get_query_stats` |
| **Parameters** | `{"query": "{app=\"payment-service\"}", "start": "now-1h"}` |
| **Internal action** | Calls `GET /loki/api/v1/index/stats`. Returns streams, chunks, entries, and bytes. |
| **Expected output** | `{"streams": N, "chunks": N, "entries": N, "bytes": N, "human_bytes": "X.XX MB", "exceeds_threshold": false}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `entries` | Non-zero — logs are being ingested |
| `streams` | Active stream count |
| `human_bytes` | Reasonable volume (not 0, not unexpectedly large) |

---

## Phase 5: Latest Logs

### Step 5.1: Fetch Recent Logs

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the latest 10 logs from "payment-service".` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"payment-service\"}", "start": "now-15m", "end": "now", "limit": 10}` |
| **Internal action** | (1) Validates stream selector. (2) Parses time range. (3) Validates time window. (4) Pre-checks cost. (5) Calls `GET /loki/api/v1/query_range`. (6) Formats log entries. |
| **Expected output** | `{"result_type": "streams", "streams": [...], "total_lines": N, "truncated": false}` |

**What to check:**

| Field | What to Verify |
|-------|----------------|
| `total_lines` | Should be > 0 — confirms logs are arriving |
| `streams` | Log lines with timestamps — verify they're recent |

---

## Phase 6: Backend Configuration

### Step 6.1: Check Guardrails

| Field | Value |
|-------|-------|
| **Prompt** | `What are the current query guardrails?` |
| **Resource** | `loki://config/guardrails` |
| **Internal action** | Returns current safety thresholds as JSON |
| **Expected output** | `{"max_query_bytes": 5000000000, "max_query_bytes_human": "5.0 GB", "max_time_window_hours": 336, "max_log_limit": 5000, "high_cardinality_threshold": 10000}` |

### Step 6.2: Check Backend Profile

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the configured Loki backend connection details.` |
| **Resource** | `loki://config/backends` |
| **Internal action** | Returns backend connection profile (URL, timeout, auth type, org ID) |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Loki reachable and healthy | `loki://system/health` | Ready for queries |
| ✅ Label taxonomy verified | `get_cluster_labels` | Expected labels present |
| ✅ Service has active streams | `get_active_series` | Streams confirmed |
| ✅ Log volume verified | `get_query_stats` | Non-zero entries and bytes |
| ✅ Recent logs arriving | `execute_logql_query` | Fresh log lines returned |
| ✅ Guardrails understood | `loki://config/guardrails` | Safety thresholds known |

**Next step →** [Log Structure Analysis](LOKI_LOG_STRUCTURE_TEST_GUIDE.md): Discover log format, structured fields, and patterns to build optimal LogQL pipelines.
