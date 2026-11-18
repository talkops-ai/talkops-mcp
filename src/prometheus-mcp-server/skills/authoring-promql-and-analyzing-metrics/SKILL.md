---
name: authoring-promql-and-analyzing-metrics
description: Discovers Prometheus metric schemas, authors and lints type-safe PromQL 3.0 queries (classic and native histograms, UTF-8 OTel selectors, vector joins, subqueries, and zero-fill ratios), and analyzes instant, range, or period-over-period time series. Use when asked to write, lint, fix, or execute a PromQL query, explore available metrics and labels, calculate percentiles or rates, compare current vs historical baseline windows, or render time-series charts. Do not use for authoring or deploying PrometheusRule CRDs and alert unit tests (use authoring-and-testing-prometheus-rules), incident RED/SLO burn-rate triage (use triaging-prometheus-incidents-and-slos), TSDB cardinality FinOps relabeling (use optimizing-tsdb-cardinality-and-finops), LogQL log queries (use authoring-logql-and-analyzing-logs), or TraceQL queries (use authoring-traceql-and-metrics-queries).
license: Apache-2.0
metadata:
  author: talkops
  version: "0.2.0"
  domain: observability
  component: prometheus
---

# Authoring PromQL and Analyzing Metrics

Guides schema-first PromQL 3.0 query construction, offline linting, preflight validation, and condensed statistical analysis. Never guess metric or label names, and never shell out to raw `curl` or `promtool` when Prometheus MCP resources and tools are available.

## MCP Execution Primitives Used

- **Resources**:
  - `prom://system/backends` and `prom://system/backends/{backend_id}` — verify active backend ID (`default` unless specified) and Prometheus version/health.
  - `prom://metadata/catalog` — live catalog of metric names, types (`counter`, `gauge`, `histogram`, `summary`), and `HELP` descriptions.
  - `prom://config/runtime` — inspect `scrape_interval` and `evaluation_interval` to size `rate()` windows properly ($\ge 4\times$ `scrape_interval`).
- **Tools (`query` toolset)**:
  - `prom_explore_metrics` — search metrics by `metric_pattern`, inspect per-job metrics (`job`), inspect label value topology (`label_name`), or paginate series label sets (`match_selector`, `cursor`).
  - `prom_query_instant` — run preflight validation (`validate_only=True`) or point-in-time queries with `detail="summary"` (5-field condensed items) or `detail="full"`.
  - `prom_query_range` — execute range queries over `[start, end]` with server-side `stats` (`min`, `max`, `avg`, `p95`, `latest`, `delta_pct`) and optional A2UI chart output (`include_chart=True`).
  - `prom_compare_periods` — compare a PromQL expression between `[current_start, current_end]` and a shifted historical window (`baseline_offset` such as `"1h"`, `"1d"`, `"7d"`), returning `pct_change`, `z_score`, and `SIGNIFICANT_SPIKE` / `SIGNIFICANT_DROP` observations.

## Step-by-Step Workflow

### 1. Discover Metric Schema & Scrape Interval `[HIGH FREEDOM]`
1. **Unbounded Selector Refusal**: Strictly **refuse** to execute unbounded full-TSDB regex scans such as `{__name__=~".*"}`, `{__name__=~".+"}`, or `{__name__=~"..*"}` in `prom_query_instant` or `prom_query_range` because they scan every series in TSDB and risk querier OOM. Instead, read `prom://metadata/catalog` or call `prom_explore_metrics(backend_id="default", metric_pattern=..., limit=50)` (using `cursor` pagination when browsing).
2. Read `prom://metadata/catalog` or call `prom_explore_metrics(backend_id="default", metric_pattern="<keyword>")` and `prom_explore_metrics(backend_id="default", label_name="<metric_name>")` to verify exact metric and label names before writing PromQL.
3. Read `prom://config/runtime` when sizing `rate()` windows; always set `rate()` range windows to at least $4\times \text{scrape\_interval}$ (typically `2m` or `5m`).

### 2. Construct, Lint & Preflight-Validate Type-Safe PromQL 3.0 `[MEDIUM FREEDOM]`
Consult [references/promql-3-syntax-and-functions.md](references/promql-3-syntax-and-functions.md) and [references/anti-patterns-and-pitfalls.md](references/anti-patterns-and-pitfalls.md):
1. **Core PromQL Rules**:
   - **Counters** (`*_total`, `*_count`, `*_sum`, `*_bucket`): Always apply `rate(m[5m])`, `irate(m[5m])`, or `increase(m[1h])` **inside** `sum()`, `avg()`, or `topk()` — never `rate(sum(m)[5m:1m])` (counter-reset spike bug!). Use `rate()` for alerting, SLOs, and trends; reserve `irate()` strictly for volatile short-window zoom-ins.
   - **Classic vs. Native Histograms**:
     - Classic `*_bucket` histogram: `histogram_quantile(0.95, sum by (le, service_name) (rate(http_server_request_duration_seconds_bucket[5m])))` (always retain `le` in `by (...)`!).
     - Prometheus 3.0 Native Histogram & UTF-8 selectors: `histogram_quantile(0.99, sum by ("service.name") (rate({"http.server.request.duration", "service.name"="frontend", "service.namespace"="otel-demo"}[5m])))` and `histogram_fraction(0, 0.2, sum by ("service.name") (rate({"http.server.request.duration", "service.name"="frontend"}[5m])))` (no `_bucket` suffix and no `le` label).
     - Pre-computed Summary `quantile="..."` series cannot be averaged across instances; migrate to histograms or use `_sum` / `_count` for mean latency.
   - **Empty-Vector Zero-Fill & Division-by-Zero Protection**: When computing error ratios (`errors / total`), preserve healthy `0.0` series via `(error_rate or on(service_name) (0 * total_rate)) / clamp_min(total_rate, 1e-9)`.
   - **Many-to-One Joins (`kube_pod_info`)**: Filter cAdvisor hierarchy noise (`container!="", image!=""`) and deduplicate `kube_pod_info` via `max by (namespace, pod, node) (kube_pod_info{...})` before `* on (namespace, pod) group_left (node)` to prevent `many-to-many matching not allowed` errors when multiple `kube-state-metrics` targets exist.
2. **Deterministic Offline Linting & Preflight Check**:
   - Run [scripts/lint_promql.py](scripts/lint_promql.py) on candidate or user-supplied queries:
     ```bash
     python3 .agents/skills/authoring-promql-and-analyzing-metrics/scripts/lint_promql.py \
       --query 'histogram_quantile(0.95, sum by (le, service_name) (rate(http_server_request_duration_seconds_bucket[5m])))'
     ```
     *(If running outside `.agents/skills`, invoke `./scripts/lint_promql.py` relative to this skill directory.)*
   - Validate syntax and counter rules server-side via `prom_query_instant(backend_id="default", query=..., validate_only=True)` before executing complex or Prometheus 3.0 UTF-8 queries.

### 3. Execute Queries & Protect Context Budget `[HIGH FREEDOM]`
1. For point-in-time rankings, subqueries (`max_over_time(sum by (service_name) (rate(...[5m]))[24h:1m])`), or status checks, call `prom_query_instant(backend_id="default", query=..., detail="summary")`.
2. For trend analysis or charts, call `prom_query_range(backend_id="default", query=..., start="-1h", end="now", detail="summary", include_chart=True)` (only use `detail="full"` if raw sample arrays are explicitly requested).
3. For period-over-period / week-over-week comparisons, call `prom_compare_periods(backend_id="default", query=..., current_start="-1h", current_end="now", baseline_offset="7d", step="1m")`.
4. **Cardinality & Truncation Discipline**: When `_truncation_advice` is returned or thousands of pod/container series match, **never** blindly raise `limit` to dump raw series; aggregate server-side in PromQL with `topk(10, sum by (namespace, pod) (rate(...[5m])))` and `detail="summary"`.

## Reference Documentation

- [PromQL Anti-Patterns and Common Pitfalls](references/anti-patterns-and-pitfalls.md)
- [PromQL 3.0 Syntax, Native Histograms, and Function Reference](references/promql-3-syntax-and-functions.md)
