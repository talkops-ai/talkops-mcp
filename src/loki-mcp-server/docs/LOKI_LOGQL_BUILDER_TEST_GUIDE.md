# LogQL Query Builder Test Guide — Loki MCP Server

**Phase 4 of 7** in the Loki end-to-end journey.
**Previous phase**: [Log Structure Analysis](LOKI_LOG_STRUCTURE_TEST_GUIDE.md)
**Next phase**: [Schema Exploration](LOKI_SCHEMA_EXPLORATION_TEST_GUIDE.md)

> After understanding log structure (Phase 3), this phase constructs LogQL queries
> from natural language intent — discovering available labels and fields,
> consulting syntax references, pre-checking cost, and executing the query.

---

## Prerequisites (Completed in Phase 3)

| Component | Status |
|-----------|--------|
| ✅ Log format known | `get_detected_fields` — JSON/logfmt/plain confirmed |
| ✅ Available fields known | `get_detected_fields` — field names, types, parsers |
| ✅ Patterns discovered | `get_log_patterns` — recurring log shapes |

---

## The Starting Point

Phase 3 analyzed log structure. Now you want to build a LogQL query from a natural language request — for example, *"find slow HTTP requests with status 500 in the checkout service"*. You need to:

1. **Discover the environment** — what labels and values exist.
2. **Validate the selector** — confirm it matches real streams.
3. **Discover fields** — know what fields can be filtered on.
4. **Consult references** — use LogQL syntax guide and templates.
5. **Preflight the query** — check cost before executing.
6. **Execute and refine** — run and iterate.

---

## Phase 1: Environment Discovery

### Step 1.1: Discover Labels

| Field | Value |
|-------|-------|
| **Prompt** | `What labels are available in my Loki cluster?` |
| **Tool** | `get_cluster_labels` |
| **Parameters** | `{}` |
| **Internal action** | Calls `GET /loki/api/v1/labels`. Returns all label names. |
| **Expected output** | `{"labels": [...], "count": N}` |

### Step 1.2: Explore Relevant Label Values

| Field | Value |
|-------|-------|
| **Prompt** | `What services are sending logs?` |
| **Tool** | `get_label_values` |
| **Parameters** | `{"label": "app"}` |
| **Internal action** | Calls `GET /loki/api/v1/label/app/values`. Returns all distinct values. |
| **Expected output** | `{"label": "app", "values": [...], "count": N}` |

### Step 1.3: Scoped Label Values

| Field | Value |
|-------|-------|
| **Prompt** | `Show me app values scoped to the production namespace.` |
| **Tool** | `get_label_values` |
| **Parameters** | `{"label": "app", "query": "{namespace=\"production\"}"}` |
| **Internal action** | Calls `GET /loki/api/v1/label/app/values?query={namespace="production"}`. Returns values scoped to the selector. |

---

## Phase 2: Selector Validation

### Step 2.1: Validate Selector

| Field | Value |
|-------|-------|
| **Prompt** | `Validate that '{app="checkout"}' matches active streams.` |
| **Tool** | `get_active_series` |
| **Parameters** | `{"match": "{app=\"checkout\"}"}` |
| **Internal action** | Returns matching series, cardinality, and warnings. |
| **Expected output** | `{"total_series": N, "label_cardinality": {...}, "warnings": [...]}` |

**What to check:**
- `total_series` > 0 — selector matches real data
- No high-cardinality warnings — selector is efficient

---

## Phase 3: Field Discovery

### Step 3.1: Discover Filterable Fields

| Field | Value |
|-------|-------|
| **Prompt** | `What fields can I filter on in "checkout" logs?` |
| **Tool** | `get_detected_fields` |
| **Parameters** | `{"query": "{app=\"checkout\"}"}` |
| **Internal action** | Returns field names, types, cardinality, and required parsers. |

**Use the output to build your pipeline:**
- `parsers: ["json"]` → Use `| json` in your query
- `type: "int"` → Use numeric comparison: `| status_code >= 500`
- `type: "string"` → Use string comparison: `| level = "error"`
- `type: "float"` → Use numeric comparison: `| latency_ms > 500`

---

## Phase 4: Reference Consultation

### Step 4.1: LogQL Syntax Reference

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the LogQL syntax reference.` |
| **Resource** | `loki://reference/logql` |
| **Internal action** | Returns static markdown with full LogQL syntax guide |

### Step 4.2: Query Templates

| Field | Value |
|-------|-------|
| **Prompt** | `Show me common LogQL query templates.` |
| **Resource** | `loki://reference/query-templates` |
| **Internal action** | Returns common query patterns for incidents, debugging, auditing, and performance |

### LogQL Pipeline Construction

Using the discovered fields and references, construct the query:

| Intent | LogQL |
|--------|-------|
| Error logs | `{app="checkout"} |= "error"` |
| Parsed error logs | `{app="checkout"} | json | level="error"` |
| HTTP 500 errors | `{app="checkout"} | json | status_code >= 500` |
| Slow requests | `{app="checkout"} | json | latency_ms > 500` |
| Slow HTTP 500s | `{app="checkout"} | json | status_code >= 500 | latency_ms > 500` |
| Error rate | `sum(rate({app="checkout"} |= "error" [5m]))` |
| Error rate by endpoint | `sum by (path) (rate({app="checkout"} | json | level="error" [5m]))` |

---

## Phase 5: Preflight

### Step 5.1: Cost Check

| Field | Value |
|-------|-------|
| **Prompt** | `Is it safe to query "checkout" for the last hour?` |
| **Tool** | `get_query_stats` |
| **Parameters** | `{"query": "{app=\"checkout\"}", "start": "now-1h"}` |
| **Internal action** | Returns streams, chunks, entries, bytes. Compares against threshold. |
| **Expected output** | `{"exceeds_threshold": false, "human_bytes": "X.XX MB"}` |

**Decision tree:**

| `exceeds_threshold` | Action |
|---------------------|--------|
| `false` | ✅ Safe to execute |
| `true` | ⚠️ Narrow time range or add more selectors |

---

## Phase 6: Execute and Refine

### Step 6.1: Execute the Constructed Query

| Field | Value |
|-------|-------|
| **Prompt** | `Find checkout logs with status 500 and latency above 500ms in the last hour.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "{app=\"checkout\"} | json | status_code >= 500 | latency_ms > 500", "start": "now-1h", "limit": 50}` |
| **Internal action** | Full execution with guardrails, cost check, and formatted output. |
| **Expected output** | `{"result_type": "streams", "streams": [...], "total_lines": N, "truncated": false}` |

### Step 6.2: Refine If No Results

If Step 6.1 returns zero results, systematically broaden:

| Attempt | Change | Why |
|---------|--------|-----|
| 1st | Remove `latency_ms > 500` | Latency filter may be too strict |
| 2nd | Change `status_code >= 500` to `|= "error"` | Field may not exist — use line filter |
| 3rd | Remove all filters, just `{app="checkout"}` | Verify base data exists |
| 4th | Broaden time range to `now-24h` | Data may be outside the window |

### Step 6.3: Metric Query Variant

| Field | Value |
|-------|-------|
| **Prompt** | `Show me the error rate over time for "checkout" with status 500.` |
| **Tool** | `execute_logql_query` |
| **Parameters** | `{"query": "sum(rate({app=\"checkout\"} | json | status_code >= 500 [5m]))", "start": "now-6h", "step": "5m"}` |
| **Internal action** | Executes as metric query. Returns matrix with time series. |
| **Expected output** | `{"result_type": "matrix", "series": [...], "total_series": 1}` |

---

## Phase Summary

At the end of this phase, you've:

| What | Tool / Resource | Status |
|------|----------------|--------|
| ✅ Environment discovered | `get_cluster_labels`, `get_label_values` | Labels and values known |
| ✅ Selector validated | `get_active_series` | Matches real streams |
| ✅ Fields discovered | `get_detected_fields` | Filterable fields known |
| ✅ References consulted | `loki://reference/logql`, `loki://reference/query-templates` | Syntax and patterns available |
| ✅ Cost pre-checked | `get_query_stats` | Within threshold |
| ✅ Query executed | `execute_logql_query` | Results returned |

**Next step →** [Schema Exploration](LOKI_SCHEMA_EXPLORATION_TEST_GUIDE.md): Full cluster-wide schema exploration — labels, values, cardinality health, and log formats.
