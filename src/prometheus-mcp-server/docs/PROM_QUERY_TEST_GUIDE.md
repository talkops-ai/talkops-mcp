# Query Test Guide — Prometheus MCP Server

**Target workflow**: PromQL Querying
**Tools tested**: `prom_query_mgmt`
**Safety features**: Counter enforcement, auto-downsampling, query validation

---

## 1. Prerequisites

| Component | Status |
|-----------|--------|
| Prometheus instance | Running with scraped metrics |
| Prometheus MCP Server | Running |

---

## 2. Test Scenarios

### Scenario A: Resource-First Metric Discovery

| Step | Action | Tool / Resource |
|------|--------|-----------------|
| 1 | Find service metrics | **Resource**: `prom://topology/services/{job}/metrics` (e.g., `job="api-server"`) |
| 2 | Identify metric | Inspect the returned `help` and `type` fields to find the target metric (e.g., `http_requests_total`) |
| 3 | Explore labels | **Tool**: `prom_explore_labels(backend_id="default", metric_name="http_requests_total")` |

**Expected**:
- Step 1: Returns a JSON list of all metrics emitted by the specific service.
- Step 3: Returns `{labels: {method: ["GET", "POST", ...], status_code: ["200", "500", ...]}}`

### Scenario B: Natural Language Query Suggestion

| Step | Action | Tool |
|------|--------|------|
| 1 | Generate from intent | `prom_suggest_promql(intent="error rate for apiserver", metric_hints=["http_requests_total"])` |

**Expected**: Returns `{"query": "sum(rate(http_requests_total{job='apiserver', status=~'5..'}[5m])) / sum(rate(http_requests_total{job='apiserver'}[5m]))", "explanation": "..."}`

### Scenario C: Query Validation

| Step | Action | Tool |
|------|--------|------|
| 1 | Validate valid query | `prom_validate_promql(backend_id="default", query="rate(http_requests_total[5m])")` |
| 2 | Validate invalid query | `prom_validate_promql(backend_id="default", query="rate(http_requests_total[")` |

**Expected**:
- Step 1: `{valid: true, error: null}`
- Step 2: `{valid: false, error: "<parse error>"}`

### Scenario D: Counter Enforcement

| Step | Action | Tool | Expected |
|------|--------|------|----------|
| 1 | Raw counter (blocked) | `prom_query_instant(backend_id="default", query="http_requests_total")` | **Error**: counter must use rate()/increase() |
| 2 | Wrapped counter (ok) | `prom_query_instant(backend_id="default", query="rate(http_requests_total[5m])")` | Success with vector result |
| 3 | Raw counter (override) | `prom_query_instant(backend_id="default", query="http_requests_total", allow_raw_counters=true)` | Success (override) |
| 4 | Gauge (no enforcement) | `prom_query_instant(backend_id="default", query="process_resident_memory_bytes")` | Success — gauges are not blocked |

### Scenario E: Range Query with Auto-Downsampling

| Step | Action | Tool |
|------|--------|------|
| 1 | Range query (no step) | `prom_query_range(backend_id="default", query="rate(http_requests_total[5m])", start=1715000000, end=1715003600)` |
| 2 | Range query (custom step) | `prom_query_range(backend_id="default", query="rate(http_requests_total[5m])", start=1715000000, end=1715003600, step="60s")` |
| 3 | Custom max_points | `prom_query_range(backend_id="default", query="rate(http_requests_total[5m])", start=1715000000, end=1715003600, max_points_per_series=50)` |

**Expected**:
- Step 1: Auto-computed step = (3600) / 200 = 18s; result has ≤200 data points per series
- Step 2: Uses explicit 60s step
- Step 3: Auto-computed step = (3600) / 50 = 72s

### Scenario F: Error Cases

| Step | Action | Expected Error |
|------|--------|----------------|
| 1 | Missing query | `prom_query_instant(backend_id="default")` | "requires 'query' parameter" |
| 2 | Missing start/end | `prom_query_range(backend_id="default", query="up")` | "requires 'start' and 'end'" |
| 3 | Missing metric_name | `prom_explore_labels(backend_id="default")` | "requires 'metric_name'" |

---

## 3. Natural Language Prompts

```text
Validate this PromQL query before running it: sum by (job) (rate(http_requests_total[5m]))
```

```text
What is the current request rate for the "api-server" job on backend "default"?
```

```text
Show me the request rate trend over the last hour for all jobs.
```

```text
What labels and values does the metric http_requests_total have?
```

```text
Show me the average request duration latency trend for the traefik service over the last 30 minutes, grouped by 1 minute intervals.
```

```text
Guide me through safely querying the up metric on backend "default".
```
