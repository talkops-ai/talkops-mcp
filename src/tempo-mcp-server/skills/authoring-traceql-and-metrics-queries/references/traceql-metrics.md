# TraceQL Metrics Reference (`rate`, `quantile_over_time`, `compare`, `topk`)

## Table of Contents

1. [Server Prerequisites](#1-server-prerequisites)
2. [Core Time-Series Aggregations](#2-core-time-series-aggregations)
3. [Top-K Ranking (`topk`)](#3-top-k-ranking-topk)
4. [Automated Cohort Comparison (`compare`)](#4-automated-cohort-comparison-compare)

## 1. Server Prerequisites

TraceQL Metrics endpoints (`/api/metrics/query_range` via `tempo_traceql_metrics_range` and `/api/metrics/query` via `tempo_traceql_metrics_instant`) require the `local-blocks` processor in `metrics_generator.processors`. Verify this in `tempo://deployment/overview` or `tempo_get_diagnostics` (absence emits `METRICS_GENERATOR_PROCESSOR_ABSENT`).

## 2. Core Time-Series Aggregations

- **Request / Error Rate**:
  - `{ resource.service.name = "checkout" } | rate()`
  - `{ resource.service.name = "checkout" && status = error } | rate() by (span.http.route)`
- **Span Count Over Time**:
  - `{ resource.service.name = "checkout" } | count_over_time() by (status)`
- **Duration Quantiles**:
  - `{ resource.service.name = "checkout" } | quantile_over_time(duration, 0.99) by (span.http.route)`
  - `{ resource.service.name = "checkout" } | quantile_over_time(duration, 0.5, 0.9, 0.95, 0.99)`
- **Duration Histogram / Sum / Avg / Min / Max**:
  - `{ resource.service.name = "checkout" } | histogram_over_time(duration)`
  - `{ resource.service.name = "checkout" } | avg_over_time(duration) by (resource.k8s.pod.name)`
  - `{ resource.service.name = "checkout" } | max_over_time(duration)`

## 3. Top-K Ranking (`topk`)

Chain `| topk(K)` after a grouped metrics aggregation to retain only the top `K` highest-value series:
- `{ status = error } | rate() by (resource.service.name, span.http.route) | topk(10)`
- `{ kind = server } | quantile_over_time(duration, 0.99) by (resource.service.name) | topk(5)`

## 4. Automated Cohort Comparison (`compare`)

Use `compare()` (directly via `tempo_compare_span_cohorts` or `tempo_traceql_metrics_instant`) to contrast attribute distributions in a failing/slow selection against the baseline population:
- Syntax: `{ <base_selector> } | compare({ <selection_selector> }, <top_n>)`
- Error cohort example: `{ resource.service.name = "checkout" } | compare({ status = error }, 10)`
- Tail latency cohort example: `{ resource.service.name = "checkout" } | compare({ duration > 1s }, 10)`
