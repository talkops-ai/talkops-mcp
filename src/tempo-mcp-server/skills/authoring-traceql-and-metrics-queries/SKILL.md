---
name: authoring-traceql-and-metrics-queries
description: Authors, validates, and optimizes TraceQL 2.x/3.x search queries, TraceQL Metrics aggregations (`rate`, `quantile_over_time`, `histogram_over_time`, `topk`, `compare`), structural parent-child/sibling operators (`>`, `>>`, `~`, `!>`, `!>>`), event/link scopes, and A2UI trace waterfall views in Grafana Tempo. Use when constructing or linting TraceQL expressions, handling OTel v1.20 vs v1.24+ semantic conventions, paginating search results, or rendering waterfall views. Do not use for PromQL queries (use authoring-promql-and-analyzing-metrics), LogQL queries (use authoring-logql-and-analyzing-logs), two-trace latency diffs (use investigating-tempo-latency-regressions), or Tempo cluster health diagnostics (use diagnosing-tempo-ingestion-and-health).
---

# Authoring TraceQL and Metrics Queries

## Preconditions

- Read `tempo://server/capabilities`, `tempo://deployment/overview`, and `tempo://schema/{backend_id}/attributes` (or call `tempo_get_attribute_names`) via MCP resources/tools before authoring any TraceQL expression.
- Verify attribute values with `tempo_get_attribute_values` before hardcoding string literals in selectors.

## Query Authoring Workflow Checklist

- [ ] **Step 1 — Discover Scoped Attributes**: Read `tempo://schema/default/attributes` (or `tempo://schema/<backend_id>/attributes` via `read_resource`) first for instant SemConv and K8s attribute presence, then call `tempo_get_attribute_names` across `scope="resource"`, `scope="span"`, `scope="event"`, `scope="link"`, or `scope="instrumentation"` as needed.
- [ ] **Step 2 — Check OTel Semconv Dual-Schema**: Consult [otel-semconv-and-k8s-attributes.md](references/otel-semconv-and-k8s-attributes.md) to verify whether the deployment emits OTel v1.20 (`http.status_code`, `net.peer.name`, `db.system`) or OTel v1.24+ (`http.response.status_code`, `server.address`, `db.system.name`) attributes.
- [ ] **Step 3 — Compose TraceQL Selector & Structural Pipeline**: Consult [traceql-syntax.md](references/traceql-syntax.md) and [query-pack.md](references/query-pack.md) to construct span-set filters, structural operators (`>`, `>>`, `~`, `!>`, `!>>`), `select()`, `by()`, `coalesce()`, and `with(most_recent=true)` hints. Whenever a target namespace is specified, include an explicit namespace resource predicate (`resource.service.namespace = "<ns>"` or `resource.k8s.namespace.name = "<ns>"`) in the TraceQL selector in addition to passing `tenant` on multi-tenant backends.
- [ ] **Step 4 — Add TraceQL Metrics Aggregations (When Needed)**: Verify `local-blocks` is active in `tempo://server/capabilities` or `tempo_get_diagnostics`, then follow [traceql-metrics.md](references/traceql-metrics.md) when computing `rate()`, `count_over_time()`, `quantile_over_time()`, `histogram_over_time()`, `sum_over_time()`, `avg_over_time()`, `min_over_time()`, `max_over_time()`, `topk()`, or `compare()`. If `local-blocks` is disabled (`METRICS_GENERATOR_PROCESSOR_ABSENT`), fall back cleanly to bounded `tempo_traceql_search` sampling and show how to enable `local-blocks`.
- [ ] **Step 5 — Lint Query Before Execution**: `[GATE]` Run `scripts/lint_traceql.py --query '<traceql>'` to validate balanced braces, unquoted `status`/`kind` intrinsic enums, explicit `resource.`/`span.` attribute scopes, and bounded regex usage before invoking `tempo_traceql_search`, `tempo_traceql_metrics_range`, `tempo_traceql_metrics_instant`, or `tempo_query_a2ui`.
- [ ] **Step 6 — Execute, Visualize & Paginate**:
  - For trace search: call `tempo_traceql_search` with `most_recent=True` for interactive triage; when `truncated == True` or `len(traces) == limit`, paginate deterministically by passing the returned `next_window` (`"<start>..<end>"` epoch range in `since`) rather than raising `limit`/`spss` unboundedly.
  - For time-series metrics: call `tempo_traceql_metrics_range`.
  - For instant top-K or cohort comparisons: call `tempo_traceql_metrics_instant` or `tempo_compare_span_cohorts`.
  - For interactive waterfall / flamegraph views of a specific `trace_id`: call `tempo_query_a2ui` instead of dumping raw span JSON.

## References & Offline Scripts

- Complete TraceQL 2.x/3.x language syntax: [traceql-syntax.md](references/traceql-syntax.md)
- TraceQL Metrics functions (`rate`, `quantile_over_time`, `compare`, `topk`): [traceql-metrics.md](references/traceql-metrics.md)
- OTel v1.20 vs v1.24+ dual-schema and Kubernetes attributes: [otel-semconv-and-k8s-attributes.md](references/otel-semconv-and-k8s-attributes.md)
- Copy-ready production TraceQL query pack: [query-pack.md](references/query-pack.md)
- Offline TraceQL syntax and performance linter: `scripts/lint_traceql.py`
