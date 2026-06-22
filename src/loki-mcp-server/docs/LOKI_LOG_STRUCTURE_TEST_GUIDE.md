# Log Structure Analysis Test Guide — Loki MCP Server

**Phase 3 of 7** in the Loki end-to-end journey.
**Previous phase**: [Service Health Check](LOKI_HEALTH_CHECK_TEST_GUIDE.md)
**Next phase**: [LogQL Query Builder](LOKI_LOGQL_BUILDER_TEST_GUIDE.md)

> After verifying health (Phase 2), this phase discovers the log format, structured
> fields, and recurring patterns for a service. The output tells you exactly which
> LogQL parser to use (`| json`, `| logfmt`, `| pattern`) and which fields are available
> for filtering and aggregation.

---

## Prerequisites (Completed in Phase 2)

| Component | Status |
|-----------|--------|
| ✅ Loki reachable | `loki://system/health` — healthy |
| ✅ Service has active streams | `get_active_series` — streams confirmed |
| ✅ Recent logs arriving | `execute_logql_query` — log lines returned |

---

## The Starting Point

Phase 2 confirmed health. Now you want to understand the log structure of a service before building LogQL pipelines. You need to answer:

1. **What format are the logs?** — JSON, logfmt, plain text, or mixed?
2. **What fields are available?** — Which keys can I filter on?
3. **What parser should I use?** — `| json`, `| logfmt`, or `| pattern`?
4. **What patterns exist?** — What are the recurring log shapes?

---

## Phase 1: Field Discovery

### Step 1.1: Validate Service Exists

| Field | Value |
|-------|-------|
| **Prompt** | `Validate that '{app="api-gateway"}' has active log streams.` |
| **Tool** | `get_active_series` |
| **Parameters** | `{"match": "{app=\"api-gateway\"}"}` |
| **Internal action** | Calls `GET /loki/api/v1/series`. Confirms the service has active streams. |
| **Expected output** | `{"matcher": "{app=\"api-gateway\"}", "total_series": N, ...}` where `total_series` > 0 |

### Step 1.2: Discover Structured Fields

| Field | Value |
|-------|-------|
| **Prompt** | `What fields can I query in "api-gateway" logs?` |
| **Tool** | `get_detected_fields` |
| **Parameters** | `{"query": "{app=\"api-gateway\"}"}` |
| **Internal action** | Calls `GET /loki/api/v1/detected_fields?query={app="api-gateway"}`. Scans log lines and returns discovered JSON/logfmt field names, their inferred types, estimated cardinality, and the parser(s) needed to extract them. |
| **Expected output** | See table below |

**Expected fields output example:**

| label | type | cardinality | parsers |
|-------|------|-------------|---------|
| `level` | string | 4 | `["json"]` |
| `msg` | string | 250 | `["json"]` |
| `status_code` | int | 15 | `["json"]` |
| `latency_ms` | float | 500 | `["json"]` |
| `method` | string | 5 | `["json"]` |
| `path` | string | 100 | `["json"]` |

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `total_fields` | Non-zero — confirms logs have structured content |
| `parsers` | Consistent parser type tells you the log format |
| `type` | Field types determine which LogQL operators you can use (`=` for string, `>` for int/float) |

### Step 1.3: Discover Fields with Custom Scope

| Field | Value |
|-------|-------|
| **Prompt** | `Discover fields in "api-gateway" logs from the last 30 minutes, scanning up to 500 lines.` |
| **Tool** | `get_detected_fields` |
| **Parameters** | `{"query": "{app=\"api-gateway\"}", "start": "now-30m", "line_limit": 500}` |
| **Internal action** | Same as 1.2 but with custom time range and higher scan limit for better coverage |

---

## Phase 2: Pattern Discovery

### Step 2.1: Discover Log Patterns

| Field | Value |
|-------|-------|
| **Prompt** | `What are the structural log patterns for "api-gateway"?` |
| **Tool** | `get_log_patterns` |
| **Parameters** | `{"query": "{app=\"api-gateway\"}", "start": "now-3h"}` |
| **Internal action** | Calls `GET /loki/api/v1/patterns?query={app="api-gateway"}&start=<epoch>&end=<epoch>`. Returns structural patterns mined by Loki's pattern ingester. Sorts by frequency descending. Auto-generates `| pattern` parser suggestions. |
| **Expected output** | See table below |

**Expected patterns output example:**

```json
{
  "patterns": [
    {"pattern": "<_> level=<_> msg=\"<_>\" status=<_> latency=<_>", "total_count": 15234},
    {"pattern": "<_> [INFO] <_> handled request <_>", "total_count": 8912},
    {"pattern": "<_> [ERROR] <_> failed: <_>", "total_count": 342}
  ],
  "total_patterns": 3,
  "suggested_parsers": [
    "| pattern \"<_> level=<_> msg=\\\"<_>\\\" status=<_> latency=<_>\"",
    "| pattern \"<_> [INFO] <_> handled request <_>\"",
    "| pattern \"<_> [ERROR] <_> failed: <_>\""
  ]
}
```

**What to check in the output:**

| Field | What to Verify |
|-------|----------------|
| `patterns` | Recurring log shapes — confirms data exists |
| `total_count` | Frequency per pattern — high counts indicate dominant formats |
| `suggested_parsers` | Ready-to-use `| pattern` expressions |
| `total_patterns` | Number of distinct patterns |

> **Note:** Pattern data is ephemeral — typically covers the last 3 hours only. If you get a 404, the pattern ingester is not enabled in your Loki deployment (`pattern_ingester.enabled: true`).

---

## Phase 3: Raw Log Sampling

### Step 3.1: Sample Raw Logs

| Field | Value |
|-------|-------|
| **Prompt** | `Show me 5 raw log lines from "api-gateway".` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"api-gateway\"}", "start": "now-15m", "limit": 5}` |
| **Internal action** | Fetches raw log lines without any parser pipeline. This lets you visually confirm the log format. |
| **Expected output** | `{"result_type": "streams", "streams": [...], "total_lines": 5}` |

**Why sample raw logs?**
- Visual confirmation of format (JSON vs logfmt vs plain text)
- Verify that `get_detected_fields` results match actual log content
- Identify edge cases or mixed formats

---

## Phase 4: Parser Validation

### Step 4.1: Test JSON Parser

| Field | Value |
|-------|-------|
| **Prompt** | `Show me "api-gateway" logs parsed as JSON, filtered to errors only.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"api-gateway\"} | json | level=\"error\"", "start": "now-1h", "limit": 10}` |
| **Internal action** | Tests the `| json` parser pipeline with a label filter. If logs are JSON, this returns parsed entries with extracted fields. |

### Step 4.2: Test Logfmt Parser (Alternative)

| Field | Value |
|-------|-------|
| **Prompt** | `Show me "api-gateway" logs parsed as logfmt.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"api-gateway\"} | logfmt", "start": "now-15m", "limit": 5}` |

### Step 4.3: Test Pattern Parser (Alternative)

| Field | Value |
|-------|-------|
| **Prompt** | `Show me "api-gateway" logs parsed with the top pattern.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"api-gateway\"} | pattern \"<_> level=<level> msg=\\\"<msg>\\\" status=<status> latency=<latency>\"", "start": "now-15m", "limit": 5}` |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool | Status |
|------|------|--------|
| ✅ Structured fields discovered | `get_detected_fields` | Field names, types, parsers known |
| ✅ Log patterns discovered | `get_log_patterns` | Recurring shapes identified |
| ✅ Raw logs sampled | `execute_logql_query` (no parser) | Format visually confirmed |
| ✅ Parser validated | `execute_logql_query` (with parser) | Correct parser identified and tested |

**Next step →** [LogQL Query Builder](LOKI_LOGQL_BUILDER_TEST_GUIDE.md): Build LogQL queries from natural language intent using discovered labels, fields, and references.
