# Interpreting Trace Diffs (`tempo_compare_traces`)

Use these rules to classify the structural and timing deltas returned by `tempo_compare_traces`.

## 1. N+1 Query / Fan-Out Regression

- **Signal**: In `operation_diffs`, a single `(service, operation)` entry shows `comparison_count / max(1, baseline_count) >= 3` while `avg_duration_delta_ms` per individual call remains flat (`< 20%` change).
- **Root Cause**: A loop issuing sequential database or RPC calls per item rather than batching.
- **TraceQL Verification**: Query `{ resource.service.name = "<service>" } && count() > <baseline_count * 2>` via `tempo_traceql_search`.

## 2. Single-Operation Slowdown

- **Signal**: `baseline_count == comparison_count`, `only_in_comparison` is empty, and a single entry in `operation_diffs` accounts for `>= 60%` of `duration_delta_ms` (`total_duration_delta_ms`).
- **Root Cause**: Resource contention, slow SQL execution plan, or payload size growth in that specific operation.

## 3. New Synchronous Dependency or Retry Path

- **Signal**: `only_in_comparison` contains one or more `(service, operation)` pairs that were absent in the baseline trace, or `error_count_delta > 0` accompanied by duplicate retry spans.
- **Root Cause**: Feature flag activation, fallback code path, or client retry backoff delay.
