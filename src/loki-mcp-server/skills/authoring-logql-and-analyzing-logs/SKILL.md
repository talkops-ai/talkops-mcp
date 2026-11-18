---
name: authoring-logql-and-analyzing-logs
description: Authors, lints, cost-checks, optimizes, and executes Grafana Loki LogQL log and metric queries using the 4-stage pipeline order (stream selector, line filter, parser, metadata/unwrap), index scan preflight checks, CIDR/pattern filters, and interactive A2UI views. Use when writing or optimizing LogQL queries, computing log error ratios or unwrap latency percentiles, filtering Loki 3.x structured metadata, fixing SampleExtractionErr or slow scans, or rendering A2UI log tables and charts. Do not use for Ruler/AlertingRule alert creation (use authoring-loki-alerting-and-recording-rules), schema/pattern discovery on unknown logs (use discovering-loki-schema-and-log-structure), multi-service incident triage (use triaging-loki-incidents-and-errors), or Prometheus PromQL queries (use authoring-promql-and-analyzing-metrics).
license: Apache-2.0
metadata:
  author: TalkOps
  version: "0.2.0"
  domain: observability
  service: grafana-loki
---

# Authoring LogQL and Analyzing Logs

Use this skill to construct, lint, preflight cost-check, and execute production-grade Grafana Loki 3.x LogQL log and metric queries without triggering full-index scans, `SampleExtractionErr` aborts, or querier OOMs.

## Mandatory 4-Stage LogQL Pipeline Order

Always order LogQL stages strictly from cheapest to most expensive (see [references/logql-syntax-and-functions.md](references/logql-syntax-and-functions.md) and [references/query-templates-and-anti-patterns.md](references/query-templates-and-anti-patterns.md)):

1. **Stream Selector (`{...}`)**: Bound at least one positive non-wildcard indexed label (`{service_name="<service>", namespace="<namespace>"}`). **Never** execute empty `{}` or wildcard-only `{service_name=~".*"}`, and **never** put high-cardinality fields (`trace_id`, `order_id`, `user_id`, `k8s.pod.name`) inside `{}`.
2. **Line Filter (`|=`, `!=`, `|~`, `!~`)**: Place SIMD/Bloom-accelerated literal substring filters (`|= "ERROR"`, `|= "duration_ms"`, `|= "status=403"`) **before** any parser!
3. **Targeted Parser (`| pattern`, `| logfmt`, `| json`)**:
   - Prefer `| pattern` (`5–10x` faster than `| regexp`) for space-delimited Nginx/Envoy logs.
   - Prefer targeted extraction (`| json status="status", duration_ms="duration_ms"` or `| logfmt status, client_ip`) instead of bare `| json`.
   - **Loki 3.x Structured Metadata Shortcut**: When `k8s.pod.name`, `trace_id`, or `severity_text` already live in chunk-header `structured_metadata` (`parser: ""`), filter directly via `{service_name="<service>", namespace="<namespace>"} | k8s.pod.name="..." | severity_text="ERROR"` **without** `| json` or `| logfmt`!
4. **Label/Metadata/IP Filters & Unwrap**:
   - Use `ip("10.0.0.0/8")` for CIDR matching (`| client_ip != ip("10.0.0.0/8")`).
   - Always append `| __error__=""` immediately after `| unwrap <field>` (`| unwrap duration_ms | __error__=""`) to prevent `SampleExtractionErr`.
   - **Divide-by-Zero Protection in LogQL Ratios**: Note that `clamp_min()` is a PromQL-only function and is **rejected with HTTP 400 in LogQL**! Protect LogQL error-ratio denominators from `NaN` / divide-by-zero on idle intervals using `(sum by (...) (rate(...[5m])) > 0)` in the denominator (and `or vector(0)` on the numerator if needed).

## Step-by-Step Execution Workflow

### Step 1: Inspect Capabilities, Guardrails, References & Schema
1. Read `loki://server/capabilities`, `loki://config/guardrails`, and `loki://schema/labels` (or call `loki_get_labels`, `loki_get_label_values`, `loki_get_series`, and `loki_get_detected_fields` with `org_id` if specified) to confirm exact label and structured metadata names before querying.
2. Read [references/logql-syntax-and-functions.md](references/logql-syntax-and-functions.md) when authoring `ip()` CIDR filters, `unwrap` latency quantiles, or structured metadata filters, and read [references/query-templates-and-anti-patterns.md](references/query-templates-and-anti-patterns.md) when writing error-ratio queries or remediating LogQL anti-patterns.

### Step 2: Lint Every Candidate Query Locally (`lint_logql.py`)
Always run [scripts/lint_logql.py](scripts/lint_logql.py) before executing or rewriting LogQL queries:
```bash
python3 .agents/skills/authoring-logql-and-analyzing-logs/scripts/lint_logql.py \
  --query '{service_name="checkout", namespace="prod"} |= "ERROR" | json status="status" | status >= 500' --json
```
If the user supplies a broken or anti-pattern query (`{}`, `{trace_id="..."}`, `| json` before `|=`), lint it first, explain every defect, and lint the corrected query to confirm `valid: true` with zero warnings.

### Step 3: Mandatory Scan-Cost Preflight (`loki_get_query_stats`)
Before running `loki_query_range` (especially over `> 1h` windows or wide namespaces), call `loki_get_query_stats` and **always explicitly state the 3-zone scan-cost classification** in your response:
- **Green (`< 1 GB` scanned)**: Safe to execute directly (still add a pre-parser `|=` filter whenever parsing JSON/logfmt to avoid unnecessary CPU work).
- **Yellow (`1 GB – 10 GB` scanned)**: Explain why Yellow-zone unselective `| json` wastes querier CPU parsing every 200 OK line, add a pre-parser literal filter (`|= "ERROR"`, `|= "50"`) or structured metadata filter (`| severity_text="ERROR"`), and **re-run `loki_get_query_stats`** before calling `loki_query_range`.
- **Red (`> 10 GB` scanned or `exceeds_threshold: true`)**: **Refuse** raw execution! Narrow `{...}` stream labels (`service_name`) and push a Bloom-friendly literal `|=` filter ahead of `| json`, then re-verify with `loki_get_query_stats`.

### Step 4: Execute with Bounded Limits
- `loki_query_range`: Log streams (`max_log_lines <= 100`) or metric trends (pass explicit `step`, e.g., `step="1m"`).
- `loki_query_instant`: Point-in-time rankings and ratios (`topk(5, quantile_over_time(0.99, ...))`, `sum by (method) (rate(...[5m]))`).
- `loki_query_a2ui`: Whenever asked for an **interactive log explorer**, **visual view**, or **A2UI table/chart** (`max_log_lines <= 100` and descriptive `title`).

## Key Reference Guides & Scripts

- [references/logql-syntax-and-functions.md](references/logql-syntax-and-functions.md) — Stream selectors, line filters, parsers, structured metadata filters, `unwrap`, `ip()` CIDR matching, and binary operators.
- [references/query-templates-and-anti-patterns.md](references/query-templates-and-anti-patterns.md) — Production error-ratio, latency-quantile, OTLP severity, and anti-pattern remediation templates.
- [scripts/lint_logql.py](scripts/lint_logql.py) — Deterministic static analyzer checking empty `{}`, high-cardinality `{}` labels, parser-before-filter order, and `| __error__=""` guards.
